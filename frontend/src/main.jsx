import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { installRuntimeLogging } from "./utils/runtimeLog.js";
import "./index.css";

installRuntimeLogging();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary name="AquaSentinel app">
        <App />
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>
);
