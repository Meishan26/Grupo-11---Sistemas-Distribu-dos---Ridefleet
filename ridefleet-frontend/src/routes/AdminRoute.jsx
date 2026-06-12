import { Navigate } from "react-router-dom";

export default function AdminRoute({ children }) {
  const token = localStorage.getItem("token");

  if (!token) {
    return <Navigate to="/login" />;
  }

  let user;
  try { user = JSON.parse(localStorage.getItem("user") || "{}"); }
  catch { user = {}; }

  if (!user.isAdmin) {
    return <Navigate to="/dashboard" />;
  }

  return children;
}
