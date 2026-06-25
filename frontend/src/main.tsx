import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

type RuntimeErrorBoundaryState = {
  error: Error | null;
};

class RuntimeErrorBoundary extends React.Component<
  React.PropsWithChildren,
  RuntimeErrorBoundaryState
> {
  state: RuntimeErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): RuntimeErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Slides Reader frontend crashed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-shell app-shell--files">
          <section className="status-panel app-page-panel">
            <header className="app-page-header">
              <div>
                <p className="eyebrow">Slides Reader</p>
                <h1>前端渲染失败</h1>
                <p className="description">
                  页面启动时遇到运行时错误，请把下面的错误信息发给我。
                </p>
              </div>
            </header>
            <div className="connection-card connection-card--error">
              <span className="status-dot" />
              <div>
                <strong>{this.state.error.message}</strong>
                <p>{this.state.error.stack}</p>
              </div>
            </div>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("页面缺少 root 挂载节点。请检查 index.html。 ");
}

// React 应用从这里挂载到 HTML 中的 root 节点。
// 挂载可以理解为把 React 组件渲染到真实网页里。
rootElement.dataset.reactMounted = "true";
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <RuntimeErrorBoundary>
      <HashRouter>
        <App />
      </HashRouter>
    </RuntimeErrorBoundary>
  </React.StrictMode>,
);
