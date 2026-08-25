const TOKEN_KEY = "voyamind_jwt";
const ROLE_KEY = "voyamind_role";
const USER_KEY = "voyamind_user";

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function getAuthRole() {
  try {
    return localStorage.getItem(ROLE_KEY) || "";
  } catch {
    return "";
  }
}

export function getAuthUser() {
  try {
    return localStorage.getItem(USER_KEY) || "";
  } catch {
    return "";
  }
}

export function setAuthSession({ access_token, role, username }) {
  localStorage.setItem(TOKEN_KEY, access_token || "");
  localStorage.setItem(ROLE_KEY, role || "");
  localStorage.setItem(USER_KEY, username || "");
  window.dispatchEvent(new Event("voyamind-auth"));
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event("voyamind-auth"));
}

export function canMutate() {
  const role = String(getAuthRole() || "").toUpperCase();
  return role === "OPERATOR" || role === "ADMIN";
}
