import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import CallScreen from "./pages/CallScreen.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import { RescuerPage } from "./pages/Rescuer.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/call" element={<CallScreen />} />
        <Route path="/phone" element={<Navigate to="/call" replace />} />
        <Route path="/rescuer/:id" element={<RescuerPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </HashRouter>
  </React.StrictMode>
);
