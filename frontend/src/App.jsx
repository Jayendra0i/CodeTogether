
import {
  useState,
  useEffect,
  useRef,
} from "react";

import Editor from "@monaco-editor/react";
import axios from "axios";
import "./App.css";

// In development Vite proxies API and WebSocket traffic to the local backend.
// That lets one public tunnel expose the frontend and keep API traffic same-origin.
const API = import.meta.env.VITE_API_URL || "/api";
const WS_API = import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;

const supportedExecutionLanguages = [
  "python",
  "javascript",
  "java",
  "c",
  "cpp",
];

const cursorColors = [
  "#f97316",
  "#a78bfa",
  "#22c55e",
  "#ec4899",
  "#06b6d4",
  "#eab308",
];

function getUserColor(name = "User", index = 0) {
  // Mix the name and participant position so similarly named people still
  // receive visually distinct avatar colors in the current room.
  const hash = [...name].reduce(
    (total, char) => ((total * 31) + char.charCodeAt(0)) >>> 0,
    index + 7
  );

  return cursorColors[(hash + index * 3) % cursorColors.length];
}

function getUserInitials(name = "User") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  return parts.length > 1
    ? `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
    : parts[0].slice(0, 2).toUpperCase();
}

function getLanguage(filename) {
  const extension = filename.split(".").pop().toLowerCase();

  const languages = {
    py: "python",
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    java: "java",
    cpp: "cpp",
    c: "c",
    html: "html",
    css: "css",
    json: "json",
    sql: "sql",
    md: "markdown",
    php: "php",
    go: "go",
    rs: "rust",
  };

  return languages[extension] || "plaintext";
}

// Safely convert backend errors into readable text.
function getErrorMessage(error, fallback = "Something went wrong.") {
  const detail = error.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        const location = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";

        const message = item.msg || "Invalid value";

        return location
          ? `${location}: ${message}`
          : message;
      })
      .join(" | ");
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (detail && typeof detail === "object") {
    return detail.msg || JSON.stringify(detail);
  }

  return error.response?.data?.message ||
    error.message ||
    fallback;
}

function App() {
  // =========================
  // AUTHENTICATION STATES
  // =========================

  const [authMode, setAuthMode] = useState("login");
  const [authLoading, setAuthLoading] = useState(true);
  const [authSubmitting, setAuthSubmitting] = useState(false);

  const [authToken, setAuthToken] = useState(
    () => localStorage.getItem("codetogether_token") || ""
  );

  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [loggedInUser, setLoggedInUser] = useState(null);
  const [inviteToken, setInviteToken] = useState(() => new URLSearchParams(window.location.search).get("invite") || "");
  const [invitationToken, setInvitationToken] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [guestName, setGuestName] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [guestSubmitting, setGuestSubmitting] = useState(false);

  // =========================
  // USER AND ROOM STATES
  // =========================

  const [username, setUsername] = useState(
    () => localStorage.getItem("codetogether_username") || "Jay"
  );

  const [roomCode, setRoomCode] = useState("");
  const [activeRoom, setActiveRoom] = useState("");

  // =========================
  // EDITOR STATES
  // =========================

  const [language, setLanguage] = useState("python");
  const [filename, setFilename] = useState("main.py");

  const [code, setCode] = useState(
    "print('Hello Collaborative Editor')"
  );

  const [files, setFiles] = useState([]);
  const [activeFileId, setActiveFileId] = useState(null);

  const [newFilename, setNewFilename] = useState("");
  const [renamingFileId, setRenamingFileId] = useState(null);
  const [renameInput, setRenameInput] = useState("");

  const [message, setMessage] = useState("");
  const [wsStatus, setWsStatus] = useState("Disconnected");
  const [participants, setParticipants] = useState([]);

  const [loadingFiles, setLoadingFiles] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [autoSaveStatus, setAutoSaveStatus] = useState("");

  // =========================
  // CHAT STATES
  // =========================

  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [sendingChat, setSendingChat] = useState(false);

  // =========================
  // CODE EXECUTION STATES
  // =========================

  const [executionInput, setExecutionInput] = useState("");
  const [executionResult, setExecutionResult] = useState(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // =========================
  // REFERENCES
  // =========================

  const socketRef = useRef(null);
  const activeFileIdRef = useRef(null);
  const codeRef = useRef(code);
  const dirtyRef = useRef(false);
  const chatEndRef = useRef(null);
  const guestSessionRef = useRef(false);

  // =========================
  // RESTORE LOGIN SESSION
  // =========================

  useEffect(() => {
    const savedToken = localStorage.getItem("codetogether_token");

    if (!savedToken) {
      setAuthLoading(false);
      return;
    }

    axios.get(`${API}/auth/me`, {
      headers: {
        Authorization: `Bearer ${savedToken}`,
      },
    })
      .then((response) => {
        const user = response.data.user || response.data;

        setLoggedInUser(user);

        const displayName =
          user.username ||
          user.name ||
          user.email?.split("@")[0] ||
          "User";

        setUsername(displayName);

        localStorage.setItem(
          "codetogether_username",
          displayName
        );

        axios.defaults.headers.common.Authorization =
          `Bearer ${savedToken}`;

        setAuthToken(savedToken);
      })
      .catch((error) => {
        console.error("Session restore error:", error);

        localStorage.removeItem("codetogether_token");

        delete axios.defaults.headers.common.Authorization;

        setAuthToken("");
        setLoggedInUser(null);
      })
      .finally(() => {
        setAuthLoading(false);
      });
  }, []);

  // =========================
  // COMPLETE LOGIN
  // =========================

  const finishLogin = async (token) => {
    if (!token) {
      throw new Error(
        "Login response did not contain an access token."
      );
    }

    try {
      const response = await axios.get(`${API}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const user = response.data.user || response.data;

      localStorage.setItem("codetogether_token", token);

      axios.defaults.headers.common.Authorization =
        `Bearer ${token}`;

      setAuthToken(token);
      setLoggedInUser(user);

      const displayName =
        user.username ||
        user.name ||
        user.email?.split("@")[0] ||
        "User";

      setUsername(displayName);

      localStorage.setItem(
        "codetogether_username",
        displayName
      );

    } catch (error) {
      localStorage.removeItem("codetogether_token");

      delete axios.defaults.headers.common.Authorization;

      setAuthToken("");
      setLoggedInUser(null);

      throw error;
    }
  };

  // =========================
  // LOGIN AND SIGNUP
  // =========================

  const handleAuthSubmit = async (event) => {
    event.preventDefault();

    setAuthError("");

    const cleanEmail = authEmail.trim().toLowerCase();

    if (!cleanEmail || !authPassword) {
      setAuthError("Please enter your email and password.");
      return;
    }

    if (authMode === "signup" && !authName.trim()) {
      setAuthError("Please enter your name.");
      return;
    }

    // Password minimum length is required only for signup.
    if (authMode === "signup" && authPassword.length < 8) {
      setAuthError("Password must contain at least 8 characters.");
      return;
    }

    if (authMode === "signup" && authPassword.length > 72) {
      setAuthError("Password cannot contain more than 72 characters.");
      return;
    }

    setAuthSubmitting(true);

    try {
      if (authMode === "signup") {
        await axios.post(`${API}/auth/register`, {
          name: authName.trim(),
          email: cleanEmail,
          password: authPassword,
        });
      }

      const loginResponse = await axios.post(
        `${API}/auth/login`,
        {
          email: cleanEmail,
          password: authPassword,
        }
      );

      const token = loginResponse.data.access_token;

      if (!token) {
        throw new Error(
          "Access token not received from server."
        );
      }

      await finishLogin(token);

      setAuthPassword("");
      setAuthError("");

    } catch (error) {
      console.error("Authentication error:", error);

      setAuthError(
        getErrorMessage(
          error,
          "Authentication failed. Please try again."
        )
      );

    } finally {
      setAuthSubmitting(false);
    }
  };

  // =========================
  // LOGOUT
  // =========================

  const handleLogout = () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }

    localStorage.removeItem("codetogether_token");

    delete axios.defaults.headers.common.Authorization;

    setAuthToken("");
    setLoggedInUser(null);

    setActiveRoom("");
    setRoomCode("");

    setFiles([]);
    setParticipants([]);
    setChatMessages([]);

    setExecutionResult(null);
    setWsStatus("Disconnected");

    setAuthMode("login");
    setAuthPassword("");
    setAuthError("");
  };

  // =========================
  // KEEP REFERENCES UPDATED
  // =========================

  useEffect(() => {
    localStorage.setItem("codetogether_username", username);
  }, [username]);

  useEffect(() => {
    if (!activeRoom) {
      setInviteLink("");
      return;
    }
    const linkToken = invitationToken || inviteToken;
    if (!linkToken) return;
    const url = new URL(window.location.href);
    url.search = `?invite=${encodeURIComponent(linkToken)}`;
    setInviteLink(url.toString());
    window.history.replaceState({}, "", url.toString());
  }, [activeRoom, invitationToken, inviteToken]);

  useEffect(() => {
    activeFileIdRef.current = activeFileId;
  }, [activeFileId]);

  useEffect(() => {
    codeRef.current = code;
  }, [code]);

  useEffect(() => {
    dirtyRef.current = isDirty;
  }, [isDirty]);

  const markClean = () => {
    dirtyRef.current = false;
    setIsDirty(false);
  };

  // =========================
  // CODE EXECUTION
  // =========================

  const handleRunCode = async () => {
    if (!supportedExecutionLanguages.includes(language)) {
      setExecutionResult({
        success: false,
        output: "",
        error: `Execution is not supported for ${language}.`,
        execution_time: 0,
        exit_code: null,
      });

      return;
    }

    if (!code.trim()) {
      setExecutionResult({
        success: false,
        output: "",
        error: "Please write some code before running.",
        execution_time: 0,
        exit_code: null,
      });

      return;
    }

    if (!activeRoom) {
      setExecutionResult({
        success: false,
        output: "",
        error: "Create or join a room before running code.",
        execution_time: 0,
        exit_code: null,
      });

      return;
    }

    if (
      !socketRef.current ||
      socketRef.current.readyState !== WebSocket.OPEN
    ) {
      setExecutionResult({
        success: false,
        output: "",
        error: "Room connection is not ready. Please try again.",
        execution_time: 0,
        exit_code: null,
      });

      return;
    }

    setIsExecuting(true);
    setExecutionResult(null);

    try {
      const response = await axios.post(`${API}/execute`, {
        language,
        code,
        stdin: executionInput,
        room_code: activeRoom,
      });

      setExecutionResult(response.data);

    } catch (error) {
      console.error("Code execution error:", error);

      setExecutionResult({
        success: false,
        output: "",
        error: getErrorMessage(error, "Code execution failed."),
        execution_time: 0,
        exit_code: null,
      });

    } finally {
      setIsExecuting(false);
    }
  };

  // =========================
  // LANGUAGE SYNCHRONIZATION
  // =========================

  const handleLanguageChange = (newLanguage) => {
    setLanguage(newLanguage);
    setExecutionResult(null);

    if (activeFileIdRef.current) {
      dirtyRef.current = true;
      setIsDirty(true);
      setAutoSaveStatus("Saving language...");
    }

    const socket = socketRef.current;

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: "language",
          language: newLanguage,
          file_id: activeFileIdRef.current,
          username,
        })
      );
    }
  };

  // =========================
  // LOAD ROOM FILES
  // =========================

  const loadFiles = async (room) => {
    setLoadingFiles(true);

    try {
      const response = await axios.get(
        `${API}/rooms/${room}/files`
      );

      const roomFiles = response.data.files || [];

      setFiles(roomFiles);

      markClean();

      setAutoSaveStatus("");
      setExecutionResult(null);

      setRenamingFileId(null);
      setRenameInput("");

      if (roomFiles.length > 0) {
        const firstFile = roomFiles[0];

        setActiveFileId(firstFile.id);
        activeFileIdRef.current = firstFile.id;

        setFilename(firstFile.filename);
        setLanguage(firstFile.language);

        codeRef.current = firstFile.content || "";
        setCode(firstFile.content || "");

      } else {
        setActiveFileId(null);
        activeFileIdRef.current = null;

        setFilename("main.py");
        setLanguage("python");

        codeRef.current = "";
        setCode("");
      }

      return true;

    } catch (error) {
      console.error("Load files error:", error);

      setMessage(
        getErrorMessage(error, "Could not load files.")
      );

      return false;

    } finally {
      setLoadingFiles(false);
    }
  };

  // =========================
  // LOAD CHAT MESSAGES
  // =========================

  const loadChatMessages = async (room) => {
    try {
      const response = await axios.get(
        `${API}/chat/${room}`
      );

      const messages = Array.isArray(response.data)
        ? response.data
        : response.data.messages || [];

      setChatMessages(messages);

    } catch (error) {
      console.error("Chat loading error:", error);

      setMessage(
        getErrorMessage(error, "Could not load chat messages.")
      );
    }
  };

  // =========================
  // SEND CHAT MESSAGE
  // =========================

  const sendChatMessage = async () => {
    const cleanMessage = chatInput.trim();

    if (!activeRoom || !cleanMessage || sendingChat) {
      return;
    }

    setSendingChat(true);

    try {
      await axios.post(
        `${API}/chat/${activeRoom}/send`,
        {
          username: username.trim() || "Guest",
          message: cleanMessage,
        }
      );

      setChatInput("");

    } catch (error) {
      console.error("Chat send error:", error);

      setMessage(
        getErrorMessage(error, "Could not send chat message.")
      );

    } finally {
      setSendingChat(false);
    }
  };

  useEffect(() => {
    if (!activeRoom) {
      setChatMessages([]);
      return;
    }

    setChatMessages([]);
    loadChatMessages(activeRoom);

  }, [activeRoom]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [chatMessages]);

  // =========================
  // WEBSOCKET CONNECTION
  // =========================

  useEffect(() => {
    if (!activeRoom || !authToken) return;

    const socket = new WebSocket(
      `${WS_API}/ws/${activeRoom}?token=${encodeURIComponent(authToken)}`
    );

    socketRef.current = socket;

    socket.onopen = () => {
      setWsStatus("Connected");
      setMessage("Real-time connection established!");
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "participants") {
          setParticipants(data.participants || []);
        }

        if (data.type === "chat_message" && data.message) {
          setChatMessages((previous) => {
            const exists = previous.some(
              (item) => item.id === data.message.id
            );

            if (exists) return previous;

            return [...previous, data.message];
          });
        }

        if (data.type === "code") {
          if (
            data.file_id != null &&
            data.file_id !== activeFileIdRef.current
          ) {
            return;
          }

          const updatedContent =
            data.content || data.code || "";

          codeRef.current = updatedContent;
          dirtyRef.current = false;

          setCode(updatedContent);
          setIsDirty(false);

          setAutoSaveStatus("Remote changes received");
        }

        if (data.type === "language") {
          if (
            data.file_id != null &&
            data.file_id !== activeFileIdRef.current
          ) {
            return;
          }

          if (data.language) {
            setLanguage(data.language);
            setExecutionResult(null);

            setAutoSaveStatus(
              `Language changed to ${data.language}`
            );
          }
        }

        if (data.type === "execution_result") {
          setExecutionResult(data.result);
          setIsExecuting(false);

          setMessage(
            `Code executed by a room participant using ${data.language}.`
          );
        }

        if (data.type === "file_created") {
          if (!data.file) return;

          setFiles((previous) => {
            if (
              previous.some(
                (file) => file.id === data.file.id
              )
            ) {
              return previous;
            }

            return [...previous, data.file];
          });

          setMessage(
            `${data.file.filename} created in the room.`
          );
        }

        if (data.type === "file_renamed") {
          setFiles((previous) =>
            previous.map((file) =>
              file.id === data.file_id
                ? { ...file, filename: data.filename }
                : file
            )
          );

          if (activeFileIdRef.current === data.file_id) {
            setFilename(data.filename);
            setLanguage(getLanguage(data.filename));
          }

          setMessage(`File renamed to ${data.filename}`);
        }

        if (data.type === "file_deleted") {
          setFiles((previous) =>
            previous.filter(
              (file) => file.id !== data.file_id
            )
          );

          if (activeFileIdRef.current === data.file_id) {
            activeFileIdRef.current = null;

            setActiveFileId(null);
            setFilename("main.py");
            setLanguage("python");

            codeRef.current = "";
            setCode("");

            setExecutionResult(null);

            markClean();
            setAutoSaveStatus("");
          }

          setMessage("File deleted from the room.");
        }

      } catch (error) {
        console.error("WebSocket message error:", error);
      }
    };

    socket.onerror = () => {
      setWsStatus("Connection error");
    };

    socket.onclose = () => {
      setWsStatus("Disconnected");
      setParticipants([]);
    };

    return () => {
      socket.onclose = null;
      socket.close();

      if (socketRef.current === socket) {
        socketRef.current = null;
      }
    };

  }, [activeRoom, username, authToken]);

  // =========================
  // CREATE ROOM
  // =========================

  const createRoom = async () => {
    const cleanUsername = username.trim();

    if (!cleanUsername) {
      setMessage("Please enter your username.");
      return;
    }

    try {
      const response = await axios.post(
        `${API}/create-room`,
        {
          username: cleanUsername,
        }
      );

      const room =
        response.data.room_code ||
        response.data.room_id;

      setInvitationToken(response.data.invitation_token || "");

      setRoomCode(room);
      setParticipants([]);

      const loaded = await loadFiles(room);

      if (!loaded) return;

      setActiveRoom(room);

      setMessage("Room created successfully!");

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not create room.")
      );
    }
  };

  // =========================
  // JOIN ROOM
  // =========================

  const joinRoom = async () => {
    const cleanRoomCode = roomCode.trim().toUpperCase();

    if (!cleanRoomCode) {
      setMessage("Enter Room ID.");
      return;
    }

    try {
      const response = await axios.post(
        `${API}/join-room`,
        null,
        {
          params: {
            room_code: cleanRoomCode,
          },
        }
      );

      const joinedRoom =
        response.data.room_code ||
        response.data.room_id;

      setInvitationToken(response.data.invitation_token || "");

      setParticipants([]);

      const loaded = await loadFiles(joinedRoom);

      if (!loaded) return;

      setActiveRoom(joinedRoom);
      setRoomCode(joinedRoom);

      setMessage("Room joined successfully!");

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not join room.")
      );
    }
  };

  useEffect(() => {
    if (!inviteToken || !authToken || !loggedInUser || activeRoom || guestSessionRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const inviteResponse = await axios.get(`${API}/invite/${encodeURIComponent(inviteToken)}`);
        const response = await axios.post(`${API}/join-room`, null, { params: { room_code: inviteResponse.data.room_code } });
        const joinedRoom = response.data.room_code || response.data.room_id;
        setInvitationToken(response.data.invitation_token || inviteToken);
        const loaded = await loadFiles(joinedRoom);
        if (!cancelled && loaded) {
          setRoomCode(joinedRoom);
          setActiveRoom(joinedRoom);
          setMessage("Room joined successfully!");
        }
      } catch (error) {
        if (!cancelled) setMessage(getErrorMessage(error, "Could not join the invited room."));
      }
    })();
    return () => { cancelled = true; };
  }, [inviteToken, authToken, loggedInUser, activeRoom]);

  const joinAsGuest = async (event) => {
    event.preventDefault();
    setAuthError("");
    setGuestSubmitting(true);
    try {
      const response = await axios.post(`${API}/guest/join`, {
        invite_token: inviteToken,
        name: guestName.trim(),
        email: guestEmail.trim().toLowerCase(),
      });
      const token = response.data.access_token;
      guestSessionRef.current = true;
      setInvitationToken(inviteToken);
      axios.defaults.headers.common.Authorization = `Bearer ${token}`;
      setAuthToken(token);
      setLoggedInUser(response.data.user);
      setUsername(response.data.user.name);
      setRoomCode(response.data.room_code);
      const loaded = await loadFiles(response.data.room_code);
      if (loaded) {
        setActiveRoom(response.data.room_code);
        setMessage("You joined the coding room.");
      }
    } catch (error) {
      setAuthError(getErrorMessage(error, "Could not join this room."));
    } finally {
      setGuestSubmitting(false);
    }
  };

  const copyInviteLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
      setMessage("Invitation link copied. Send it through WhatsApp or another app.");
    } catch {
      setMessage("Copy failed. Select and copy the invitation link above.");
    }
  };

  // =========================
  // OPEN FILE
  // =========================

  const openFile = async (file) => {
    if (file.id === activeFileIdRef.current) return;

    if (dirtyRef.current) {
      setMessage(
        "Please wait for Auto-Save before switching files."
      );

      return;
    }

    try {
      const response = await axios.get(
        `${API}/files/${file.id}`
      );

      const selectedFile = response.data;

      markClean();

      setAutoSaveStatus("");
      setExecutionResult(null);

      activeFileIdRef.current = selectedFile.id;

      setActiveFileId(selectedFile.id);
      setFilename(selectedFile.filename);
      setLanguage(selectedFile.language);

      codeRef.current = selectedFile.content || "";
      setCode(selectedFile.content || "");

      setMessage(`Opened ${selectedFile.filename}`);

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not open file.")
      );
    }
  };

  // =========================
  // CREATE FILE
  // =========================

  const createFile = async () => {
    const cleanName = newFilename.trim();

    if (!activeRoom) {
      setMessage("Create or join a room first.");
      return;
    }

    if (!cleanName) {
      setMessage("Enter a filename.");
      return;
    }

    if (dirtyRef.current) {
      setMessage(
        "Please wait for Auto-Save before creating a file."
      );

      return;
    }

    try {
      const fileLanguage = getLanguage(cleanName);

      const response = await axios.post(
        `${API}/rooms/${activeRoom}/files`,
        {
          filename: cleanName,
          language: fileLanguage,
          content: "",
        }
      );

      const newFile = response.data.file || {
        id: response.data.file_id,
        filename: response.data.filename,
        language: response.data.language,
        content: response.data.content,
      };

      setFiles((previous) => {
        if (
          previous.some(
            (file) => file.id === newFile.id
          )
        ) {
          return previous;
        }

        return [...previous, newFile];
      });

      markClean();

      setAutoSaveStatus("");

      activeFileIdRef.current = newFile.id;

      setActiveFileId(newFile.id);
      setFilename(newFile.filename);
      setLanguage(newFile.language);

      codeRef.current = newFile.content || "";
      setCode(newFile.content || "");

      setExecutionResult(null);

      setNewFilename("");

      setMessage("File created successfully!");

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not create file.")
      );
    }
  };

  // =========================
  // MANUAL SAVE
  // =========================

  const saveCode = async () => {
    if (!activeRoom) {
      setMessage("Create or join a room first.");
      return;
    }

    if (!filename.trim()) {
      setMessage("Filename cannot be empty.");
      return;
    }

    setSaving(true);

    try {
      let savedFileId = activeFileId;

      if (savedFileId) {
        await axios.put(
          `${API}/files/${savedFileId}`,
          {
            filename: filename.trim(),
            language,
            content: code,
          }
        );

      } else {
        const response = await axios.post(
          `${API}/rooms/${activeRoom}/files`,
          {
            filename: filename.trim(),
            language,
            content: code,
          }
        );

        savedFileId =
          response.data.file_id ||
          response.data.file?.id;

        activeFileIdRef.current = savedFileId;

        setActiveFileId(savedFileId);
      }

      setFiles((previous) => {
        const exists = previous.some(
          (file) => file.id === savedFileId
        );

        const updatedFile = {
          id: savedFileId,
          filename: filename.trim(),
          language,
          content: code,
        };

        return exists
          ? previous.map((file) =>
              file.id === savedFileId
                ? updatedFile
                : file
            )
          : [...previous, updatedFile];
      });

      markClean();

      setAutoSaveStatus("All changes saved");
      setFilename(filename.trim());

      setMessage("File saved successfully!");

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not save file.")
      );

    } finally {
      setSaving(false);
    }
  };

  // =========================
  // AUTO SAVE
  // =========================

  useEffect(() => {
    if (!isDirty || !activeRoom || !activeFileId) {
      return;
    }

    const fileId = activeFileId;
    const currentCode = code;
    const currentFilename = filename.trim();
    const currentLanguage = language;

    setAutoSaveStatus("Unsaved changes");

    const timer = setTimeout(async () => {
      setAutoSaveStatus("Saving...");

      try {
        await axios.put(
          `${API}/files/${fileId}`,
          {
            filename: currentFilename,
            language: currentLanguage,
            content: currentCode,
          }
        );

        setFiles((previous) =>
          previous.map((file) =>
            file.id === fileId
              ? {
                  ...file,
                  filename: currentFilename,
                  language: currentLanguage,
                  content: currentCode,
                }
              : file
          )
        );

        if (
          activeFileIdRef.current === fileId &&
          codeRef.current === currentCode &&
          dirtyRef.current
        ) {
          markClean();

          setAutoSaveStatus("All changes saved");
        }

      } catch (error) {
        console.error("Auto-save error:", error);

        setAutoSaveStatus("Auto-save failed");
      }

    }, 1200);

    return () => clearTimeout(timer);

  }, [
    code,
    filename,
    language,
    activeFileId,
    activeRoom,
    isDirty,
  ]);

  // =========================
  // START RENAME
  // =========================

  const startRename = (file) => {
    setRenamingFileId(file.id);
    setRenameInput(file.filename);
  };

  // =========================
  // CANCEL RENAME
  // =========================

  const cancelRename = () => {
    setRenamingFileId(null);
    setRenameInput("");
  };

  // =========================
  // RENAME FILE
  // =========================

  const renameFile = async (file) => {
    const newName = renameInput.trim();

    if (!newName) {
      setMessage("Filename cannot be empty.");
      return;
    }

    if (newName === file.filename) {
      cancelRename();
      return;
    }

    const duplicate = files.some(
      (item) =>
        item.id !== file.id &&
        item.filename.toLowerCase() === newName.toLowerCase()
    );

    if (duplicate) {
      setMessage("A file with this name already exists.");
      return;
    }

    try {
      const newLanguage = getLanguage(newName);

      await axios.put(
        `${API}/files/${file.id}`,
        {
          filename: newName,
          language: newLanguage,
        }
      );

      setFiles((previous) =>
        previous.map((item) =>
          item.id === file.id
            ? {
                ...item,
                filename: newName,
                language: newLanguage,
              }
            : item
        )
      );

      if (activeFileIdRef.current === file.id) {
        setFilename(newName);
        setLanguage(newLanguage);

        setExecutionResult(null);

        const socket = socketRef.current;

        if (
          socket &&
          socket.readyState === WebSocket.OPEN
        ) {
          socket.send(
            JSON.stringify({
              type: "language",
              language: newLanguage,
              file_id: file.id,
              username,
            })
          );
        }
      }

      setRenamingFileId(null);
      setRenameInput("");

      setMessage(`File renamed to ${newName}`);

    } catch (error) {
      console.error("Rename error:", error);

      setMessage(
        getErrorMessage(error, "Could not rename file.")
      );
    }
  };

  // =========================
  // DELETE FILE
  // =========================

  const deleteFile = async (file) => {
    if (!window.confirm(`Delete ${file.filename}?`)) {
      return;
    }

    if (
      file.id === activeFileIdRef.current &&
      dirtyRef.current
    ) {
      setMessage(
        "Please wait for Auto-Save before deleting this file."
      );

      return;
    }

    try {
      await axios.delete(
        `${API}/files/${file.id}`
      );

      const remainingFiles = files.filter(
        (item) => item.id !== file.id
      );

      setFiles(remainingFiles);

      if (renamingFileId === file.id) {
        cancelRename();
      }

      if (activeFileIdRef.current === file.id) {
        markClean();

        setAutoSaveStatus("");
        setExecutionResult(null);

        if (remainingFiles.length > 0) {
          await openFile(remainingFiles[0]);

        } else {
          activeFileIdRef.current = null;

          setActiveFileId(null);
          setFilename("main.py");
          setLanguage("python");

          codeRef.current = "";
          setCode("");
        }
      }

      setMessage("File deleted successfully!");

    } catch (error) {
      console.error(error);

      setMessage(
        getErrorMessage(error, "Could not delete file.")
      );
    }
  };

  // =========================
  // LIVE CODE CHANGE
  // =========================

  const handleCodeChange = (value) => {
    const updatedCode = value || "";

    codeRef.current = updatedCode;
    dirtyRef.current = true;

    setCode(updatedCode);
    setIsDirty(true);

    setAutoSaveStatus("Unsaved changes");

    const socket = socketRef.current;

    if (
      socket &&
      socket.readyState === WebSocket.OPEN
    ) {
      socket.send(
        JSON.stringify({
          type: "code",
          file_id: activeFileIdRef.current,
          content: updatedCode,
          username,
        })
      );
    }
  };

  // =========================
  // AUTHENTICATION SCREEN
  // =========================

  if (authLoading) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="auth-brand">
            <span>{"</>"}</span> CodeTogether
          </div>

          <p className="auth-subtitle">
            Checking your secure session...
          </p>
        </div>
      </div>
    );
  }

  if (inviteToken && (!authToken || !loggedInUser)) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="auth-brand"><span>{"</>"}</span> CodeTogether</div>
          <h1>Join coding room</h1>
          <p className="auth-subtitle">Enter your details to join the invited coding room. No account or email verification needed.</p>
          <form className="auth-form" onSubmit={joinAsGuest}>
            <label>Your name<input value={guestName} onChange={(e) => setGuestName(e.target.value)} minLength={2} maxLength={100} required placeholder="Name shown to collaborators" /></label>
            <label>Email address<input type="email" value={guestEmail} onChange={(e) => setGuestEmail(e.target.value)} required placeholder="you@example.com" /></label>
            {authError && <p className="auth-error">{authError}</p>}
            <button className="auth-submit-btn" type="submit" disabled={guestSubmitting}>{guestSubmitting ? "Joining..." : "Join room"}</button>
          </form>
        </div>
      </div>
    );
  }

  if (!authToken || !loggedInUser) {
    return (
      <div className="auth-screen">
        <div className="auth-card">

          <div className="auth-brand">
            <span>{"</>"}</span> CodeTogether
          </div>

          <h1>
            {authMode === "login"
              ? "Welcome back"
              : "Create your account"}
          </h1>

          <p className="auth-subtitle">
            {authMode === "login"
              ? "Log in to create or join a collaborative coding room."
              : "Sign up to start coding together."}
          </p>

          <form
            className="auth-form"
            onSubmit={handleAuthSubmit}
          >

            {authMode === "signup" && (
              <label>
                Full name

                <input
                  type="text"
                  value={authName}
                  onChange={(event) =>
                    setAuthName(event.target.value)
                  }
                  placeholder="Enter your name"
                  minLength={2}
                  maxLength={100}
                  required
                />
              </label>
            )}

            <label>
              Email address

              <input
                type="email"
                value={authEmail}
                onChange={(event) =>
                  setAuthEmail(event.target.value)
                }
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>

            <label>
              Password

              <input
                type="password"
                value={authPassword}
                onChange={(event) =>
                  setAuthPassword(event.target.value)
                }
                placeholder={
                  authMode === "signup"
                    ? "At least 8 characters"
                    : "Enter your password"
                }
                minLength={authMode === "signup" ? 8 : undefined}
                maxLength={72}
                autoComplete={
                  authMode === "login"
                    ? "current-password"
                    : "new-password"
                }
                required
              />
            </label>

            {authError && (
              <p className="auth-error">
                {authError}
              </p>
            )}

            <button
              className="auth-submit-btn"
              type="submit"
              disabled={authSubmitting}
            >
              {authSubmitting
                ? "Please wait..."
                : authMode === "login"
                  ? "Log In"
                  : "Create Account"}
            </button>

          </form>

          <div className="auth-switch">

            {authMode === "login"
              ? "Don't have an account?"
              : "Already have an account?"}

            <button
              type="button"
              onClick={() => {
                setAuthMode(
                  authMode === "login"
                    ? "signup"
                    : "login"
                );

                setAuthError("");
              }}
            >
              {authMode === "login"
                ? "Sign up"
                : "Log in"}
            </button>

          </div>

          <p className="auth-google-note">
            Google sign-in will be added after a Google OAuth
            Client ID is configured.
          </p>

        </div>
      </div>
    );
  }

  // =========================
  // MAIN COLLABORATIVE EDITOR
  // =========================

  return (
    <div className="app">

      {/* TOPBAR */}

      <header className="topbar">

        <div className="brand">
          <span className="brand-icon">{"</>"}</span>
          <span>CodeTogether</span>
        </div>

        <div className="topbar-account">

          <span className="online-status">
            ● Backend connected
          </span>

          <span className="signed-in-user">
            {loggedInUser.username ||
              loggedInUser.name ||
              loggedInUser.email}
          </span>

          <button
            className="logout-btn"
            onClick={handleLogout}
          >
            Log out
          </button>

        </div>

      </header>

      <main className="workspace">

        {/* SIDEBAR */}

        <aside className="sidebar">

          <h2>Workspace</h2>

          <label>Your username</label>

          <input
            value={username}
            onChange={(e) =>
              setUsername(e.target.value)
            }
            placeholder="Enter username"
            disabled={!!activeRoom}
          />

          <button
            className="primary-btn"
            onClick={createRoom}
          >
            + Create Room
          </button>

          {activeRoom && (
            <div className="invite-link-panel">
              <label htmlFor="room-invite-link">Invitation link</label>
              <input id="room-invite-link" value={inviteLink} readOnly onFocus={(event) => event.target.select()} />
              <button className="secondary-btn" onClick={copyInviteLink}>Copy invitation link</button>
              <small>Anyone with this link can join as a guest.</small>
            </div>
          )}

          <div className="separator">
            OR JOIN EXISTING ROOM
          </div>

          <label>Room ID</label>

          <input
            value={roomCode}
            onChange={(e) =>
              setRoomCode(e.target.value.toUpperCase())
            }
            placeholder="Enter Room ID"
          />

          <button
            className="secondary-btn"
            onClick={joinRoom}
          >
            Join Room
          </button>

          {/* ACTIVE ROOM */}

          <div className="room-info">
            <h3>Active Room</h3>

            <p>
              {activeRoom || "No room selected"}
            </p>
          </div>

          {/* CONNECTION STATUS */}

          <div className="room-info">
            <h3>Connection Status</h3>

            <p>
              {wsStatus === "Connected" ? "🟢" : "🔴"}{" "}
              {wsStatus}
            </p>
          </div>

          {/* FILE EXPLORER */}

          <div className="file-explorer">

            <div className="explorer-heading">
              <h3>EXPLORER</h3>

              <span>
                {files.length} files
              </span>
            </div>

            <div className="new-file-control">

              <input
                value={newFilename}
                onChange={(e) =>
                  setNewFilename(e.target.value)
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    createFile();
                  }
                }}
                placeholder="New filename..."
                disabled={!activeRoom}
              />

              <button
                className="add-file-btn"
                onClick={createFile}
                disabled={!activeRoom}
                title="Create file"
              >
                +
              </button>

            </div>

            <div className="file-list">

              {!activeRoom ? (

                <p className="empty-files">
                  Join a room to view files.
                </p>

              ) : loadingFiles ? (

                <p className="empty-files">
                  Loading files...
                </p>

              ) : files.length === 0 ? (

                <p className="empty-files">
                  No files yet. Create your first file.
                </p>

              ) : (

                files.map((file) => (

                  <div
                    key={file.id}
                    className={`file-item ${
                      activeFileId === file.id
                        ? "active-file"
                        : ""
                    }`}
                  >

                    {renamingFileId === file.id ? (

                      <div className="file-rename-box">

                        <input
                          className="file-rename-input"
                          value={renameInput}
                          onChange={(e) =>
                            setRenameInput(e.target.value)
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              renameFile(file);
                            }

                            if (e.key === "Escape") {
                              cancelRename();
                            }
                          }}
                          autoFocus
                          aria-label="New filename"
                        />

                        <button
                          className="file-action-btn rename-save-btn"
                          onClick={() => renameFile(file)}
                          title="Save new filename"
                        >
                          ✓
                        </button>

                        <button
                          className="file-action-btn rename-cancel-btn"
                          onClick={cancelRename}
                          title="Cancel rename"
                        >
                          ×
                        </button>

                      </div>

                    ) : (

                      <>

                        <button
                          className="file-open-btn"
                          onClick={() => openFile(file)}
                          title={file.filename}
                        >
                          <span className="file-icon">
                            📄
                          </span>

                          <span className="file-label">
                            {file.filename}
                          </span>
                        </button>

                        <button
                          className="file-action-btn rename-file-btn"
                          onClick={() => startRename(file)}
                          title="Rename file"
                          aria-label={`Rename ${file.filename}`}
                        >
                          ✎
                        </button>

                        <button
                          className="delete-file-btn"
                          onClick={() => deleteFile(file)}
                          title="Delete file"
                          aria-label={`Delete ${file.filename}`}
                        >
                          ×
                        </button>

                      </>

                    )}

                  </div>

                ))

              )}

            </div>

          </div>

          {/* PARTICIPANTS */}

          
{/* PARTICIPANTS */}
<div className="room-info participants-panel">
  <h3>
    Participants ({participants.length})
  </h3>

  {participants.length === 0 ? (
    <p>No participants online</p>
  ) : (
    <div className="participants-list">
      {participants.map((person, index) => {
        const participantName =
          typeof person === "string"
            ? person
            : person?.username || person?.name || "User";

        return (
          <div
            className="participant"
            key={`${participantName}-${index}`}
          >
            <div
              className="participant-avatar"
              style={{
                backgroundColor: getUserColor(
                  participantName,
                  index
                ),
              }}
              title={participantName}
            >
              {getUserInitials(participantName)}
            </div>

            <div className="participant-details">
              <span>{participantName}</span>
              <small>🟢 Online</small>
            </div>
          </div>
        );
      })}
    </div>
  )}
</div>


          {message && (
            <p className="message">
              {message}
            </p>
          )}

        </aside>

        {/* EDITOR AREA */}

        <section className="editor-area">

          {/* EDITOR TOOLBAR */}

          <div className="editor-toolbar">

            <div className="file-name">
              <span>📄</span>

              <strong>
                {filename}
              </strong>
            </div>

            <div className="editor-actions">

              <select
                value={language}
                onChange={(e) =>
                  handleLanguageChange(e.target.value)
                }
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="typescript">TypeScript</option>
                <option value="java">Java</option>
                <option value="cpp">C++</option>
                <option value="c">C</option>
                <option value="html">HTML</option>
                <option value="css">CSS</option>
                <option value="json">JSON</option>
                <option value="sql">SQL</option>
                <option value="plaintext">Plain Text</option>
              </select>

              <button
                className="run-btn"
                onClick={handleRunCode}
                disabled={
                  isExecuting ||
                  !supportedExecutionLanguages.includes(language)
                }
                title={
                  supportedExecutionLanguages.includes(language)
                    ? "Run code"
                    : "This language cannot currently be executed"
                }
              >
                {isExecuting
                  ? "Running..."
                  : "▶ Run Code"}
              </button>

              <button
                className="save-btn"
                onClick={saveCode}
                disabled={saving}
              >
                {saving
                  ? "Saving..."
                  : "Save Code"}
              </button>

              <span className="autosave-status">
                {autoSaveStatus}
              </span>

            </div>

          </div>

          {/* MONACO EDITOR */}

          <div className="monaco-container">

            <Editor
              height="100%"
              language={language}
              theme="vs-dark"
              value={code}
              onChange={handleCodeChange}
              options={{
                minimap: {
                  enabled: false,
                },
                fontSize: 15,
                automaticLayout: true,
                scrollBeyondLastLine: false,
                wordWrap: "on",
              }}
            />

          </div>

          {/* CODE EXECUTION PANEL */}

          <section className="execution-panel">

            <div className="execution-heading">
              <h3>Program Input (stdin)</h3>

              <span>Optional</span>
            </div>

            <textarea
              className="execution-input"
              value={executionInput}
              onChange={(e) =>
                setExecutionInput(e.target.value)
              }
              placeholder="Enter program input here..."
              rows={2}
            />

            <div className="output-heading">

              <h3>Output</h3>

              {executionResult && (
                <span
                  className={
                    executionResult.success
                      ? "execution-success"
                      : "execution-failed"
                  }
                >
                  {executionResult.success
                    ? "Success"
                    : "Failed"}
                </span>
              )}

            </div>

            <div className="output-content">

              {isExecuting ? (

                <p className="output-placeholder">
                  Running your code...
                </p>

              ) : executionResult ? (

                <>

                  {executionResult.output && (
                    <pre className="program-output">
                      {executionResult.output}
                    </pre>
                  )}

                  {executionResult.error && (
                    <pre className="program-error">
                      {executionResult.error}
                    </pre>
                  )}

                  {!executionResult.output &&
                    !executionResult.error && (
                      <p className="output-placeholder">
                        Program executed with no output.
                      </p>
                    )}

                  <div className="execution-meta">

                    <span>
                      Time:{" "}
                      {executionResult.execution_time ?? 0}s
                    </span>

                    <span>
                      Exit Code:{" "}
                      {executionResult.exit_code === null
                        ? "N/A"
                        : executionResult.exit_code}
                    </span>

                  </div>

                </>

              ) : (

                <p className="output-placeholder">
                  Click Run Code to see the program output here.
                </p>

              )}

            </div>

          </section>

          {/* STATUS BAR */}

          <footer className="statusbar">

            <span>
              {language.toUpperCase()}
            </span>

            <span>
              {activeRoom
                ? `Room: ${activeRoom}`
                : "No active room"}
            </span>

            <span>
              CodeTogether Editor
            </span>

          </footer>

        </section>

        {/* ROOM CHAT PANEL */}

        <aside className="chat-panel">

          <div className="chat-header">

            <div>
              <h3>Room Chat</h3>

              <small>
                {activeRoom
                  ? `Room: ${activeRoom}`
                  : "Join a room first"}
              </small>
            </div>

            <span className="chat-online-dot">
              ●
            </span>

          </div>

          <div className="chat-messages">

            {!activeRoom ? (

              <p className="chat-empty">
                Create or join a room to start chatting.
              </p>

            ) : chatMessages.length === 0 ? (

              <p className="chat-empty">
                No messages yet. Start the conversation!
              </p>

            ) : (

              chatMessages.map((chat, index) => (

                <div
                  className={`chat-message ${
                    chat.username === username
                      ? "own-message"
                      : ""
                  }`}
                  key={chat.id || index}
                >

                  <div className="chat-message-top">

                    <strong>
                      {chat.username}
                    </strong>

                    <small>
                      {chat.created_at
                        ? new Date(
                            chat.created_at
                          ).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : ""}
                    </small>

                  </div>

                  <p>
                    {chat.message}
                  </p>

                </div>

              ))

            )}

            <div ref={chatEndRef} />

          </div>

          {/* CHAT INPUT */}

          <form
            className="chat-input-area"
            onSubmit={(e) => {
              e.preventDefault();
              sendChatMessage();
            }}
          >

            <input
              value={chatInput}
              onChange={(e) =>
                setChatInput(e.target.value)
              }
              placeholder={
                activeRoom
                  ? "Type a message..."
                  : "Join a room first"
              }
              disabled={!activeRoom || sendingChat}
              maxLength={2000}
            />

            <button
              type="submit"
              disabled={
                !activeRoom ||
                !chatInput.trim() ||
                sendingChat
              }
            >
              {sendingChat ? "..." : "Send"}
            </button>

          </form>

        </aside>

      </main>

    </div>
  );
}

export default App;
