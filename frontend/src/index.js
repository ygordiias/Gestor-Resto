import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
// StrictMode removido para evitar double-mount que causa problemas com Socket.IO
root.render(<App />);
