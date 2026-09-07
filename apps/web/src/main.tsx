import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { PhoneCapture } from "./PhoneCapture";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Application root is missing");

// A fragment is never sent to the server or referrer. Remove its bearer secret
// from the address/history immediately and retain it only in this page's memory.
const capture = window.location.hash.startsWith("#capture");
const photoToken =
  new URLSearchParams(window.location.hash.slice(1)).get("capture") ?? "";
if (capture)
  window.history.replaceState(null, "", window.location.pathname + "#capture");

createRoot(root).render(
  <StrictMode>
    {capture ? <PhoneCapture token={photoToken} /> : <App />}
  </StrictMode>,
);
