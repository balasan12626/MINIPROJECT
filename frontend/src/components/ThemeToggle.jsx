import { useEffect, useState } from "react";

const KEY = "flood_theme";

function applyTheme(theme) {
  document.body.classList.toggle("light-theme", theme === "light");
  localStorage.setItem(KEY, theme);
  window.dispatchEvent(new CustomEvent("flood-theme", { detail: theme }));
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => localStorage.getItem(KEY) || "dark");

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    function onStorage(e) {
      if (e.key === KEY && e.newValue) setTheme(e.newValue);
    }
    function onCustom(e) {
      if (e.detail && e.detail !== theme) setTheme(e.detail);
    }
    window.addEventListener("storage", onStorage);
    window.addEventListener("flood-theme", onCustom);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("flood-theme", onCustom);
    };
  }, [theme]);

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      <button type="button" className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>
        Dark
      </button>
      <button type="button" className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>
        Light
      </button>
    </div>
  );
}
