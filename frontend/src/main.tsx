import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initObservability } from "./observability";
import "./styles.css";

// Vite freezes import.meta.env at build time, so VITE_OTEL_ENABLED must be
// set when the production image is built — there is no runtime opt-in.
// The dev image leaves it unset, so this is a no-op locally.
initObservability();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
