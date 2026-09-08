import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Entry } from "./Entry";
import { capturePhotoToken } from "./photo-authority";
import { captureSetupAuthority } from "./setup-authority";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Application root is missing");

// A fragment is never sent to the server or referrer. Remove its bearer secret
// from the address/history immediately and retain it only in this page's memory.
const photoToken = capturePhotoToken();
const setupAuthority = captureSetupAuthority();

createRoot(root).render(
  <StrictMode>
    <Entry photoToken={photoToken} setupAuthority={setupAuthority} />
  </StrictMode>,
);
