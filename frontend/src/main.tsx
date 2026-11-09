import "@fontsource-variable/inter/index.css";
import "@fontsource-variable/newsreader/index.css";
import "./fonts.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
