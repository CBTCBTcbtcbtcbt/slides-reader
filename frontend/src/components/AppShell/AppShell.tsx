import { useState, type ReactNode } from "react";
import { AppIcon } from "../AppIcon";

export type AppShellSection = "files" | "reader" | "wrongBook" | "phaseExam" | "settings";

type AppShellProps = {
  // activeSection 用来高亮当前主导航项。
  activeSection: AppShellSection;
  // canReturnToReader 控制“阅读”导航在没有打开文档时是否可点。
  canReturnToReader: boolean;
  // children 是当前路由页面的实际内容。
  children: ReactNode;
  // 以下回调保持现有 App.tsx 的路由和业务状态不变。
  onNavigateFiles: () => void;
  onNavigateReader: () => void;
  onNavigateWrongBook: () => void;
  onNavigatePhaseExam: () => void;
  onNavigateSettings: () => void;
};

type NavigationItem = {
  section: AppShellSection;
  label: string;
  icon: "archive" | "book" | "exam" | "wrongBook" | "settings";
  onClick: () => void;
  disabled?: boolean;
};

export function AppShell({
  activeSection,
  canReturnToReader,
  children,
  onNavigateFiles,
  onNavigateReader,
  onNavigateWrongBook,
  onNavigatePhaseExam,
  onNavigateSettings,
}: AppShellProps) {
  // 折叠状态只保存在当前页面内存中，刷新后恢复展开，符合计划中的默认假设。
  const [isCollapsed, setIsCollapsed] = useState(() => {
    // 窄屏下默认深度折叠，避免左侧栏挤压主要内容。
    if (typeof window === "undefined") {
      return false;
    }
    return typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 560px)").matches
      : false;
  });
  const navigationItems: NavigationItem[] = [
    {
      section: "files",
      label: "课件库",
      icon: "archive",
      onClick: onNavigateFiles,
    },
    {
      section: "reader",
      label: "阅读",
      icon: "book",
      onClick: onNavigateReader,
      disabled: !canReturnToReader,
    },
    {
      section: "phaseExam",
      label: "考试",
      icon: "exam",
      onClick: onNavigatePhaseExam,
    },
    {
      section: "wrongBook",
      label: "错题本",
      icon: "wrongBook",
      onClick: onNavigateWrongBook,
    },
  ];

  function renderNavigationButton(item: NavigationItem) {
    // 每个导航按钮都用 aria-current 告诉辅助技术当前所在页面。
    const isActive = activeSection === item.section;

    return (
      <button
        type="button"
        className={`app-shell-nav-button${isActive ? " app-shell-nav-button--active" : ""}`}
        key={item.section}
        onClick={item.onClick}
        disabled={item.disabled}
        aria-label={item.label}
        aria-current={isActive ? "page" : undefined}
        title={item.label}
      >
        <AppIcon name={item.icon} />
        <span>{item.label}</span>
      </button>
    );
  }

  return (
    <div
      className={`app-shell-layout${isCollapsed ? " app-shell-layout--collapsed" : ""}`}
      data-testid="app-shell"
    >
      <aside className="app-shell-rail" aria-label="主导航">
        <div className="app-shell-brand" aria-label="Slides Reader">
          SR
        </div>
        <nav className="app-shell-nav">{isCollapsed ? null : navigationItems.map(renderNavigationButton)}</nav>
        {isCollapsed ? null : (
          <button
            type="button"
            className={`app-shell-nav-button${
              activeSection === "settings" ? " app-shell-nav-button--active" : ""
            }`}
            onClick={onNavigateSettings}
            aria-label="设置"
            aria-current={activeSection === "settings" ? "page" : undefined}
            title="设置"
          >
            <AppIcon name="settings" />
            <span>设置</span>
          </button>
        )}
        <button
          type="button"
          className={`app-shell-collapse-tab${
            isCollapsed ? " app-shell-collapse-tab--collapsed" : ""
          }`}
          onClick={() => setIsCollapsed((value) => !value)}
          aria-label={isCollapsed ? "展开主导航" : "折叠主导航"}
          title={isCollapsed ? "展开主导航" : "折叠主导航"}
        >
          <AppIcon name={isCollapsed ? "chevronRight" : "chevronLeft"} />
        </button>
      </aside>
      <div className="app-shell-content">{children}</div>
    </div>
  );
}
