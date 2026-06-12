import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// React 应用从这里挂载到 HTML 中的 root 节点。
// 挂载可以理解为把 React 组件渲染到真实网页里。
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
