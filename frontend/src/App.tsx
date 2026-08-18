import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import RequireAuth from "./auth/RequireAuth";
import DashboardPage from "./pages/DashboardPage";
import EvaluationDetailPage from "./pages/EvaluationDetailPage";
import ImportModelPage from "./pages/ImportModelPage";
import LeaderboardPage from "./pages/LeaderboardPage";
import LoginPage from "./pages/LoginPage";
import ModelDetailPage from "./pages/ModelDetailPage";
import ModelsPage from "./pages/ModelsPage";
import ReportPage from "./pages/ReportPage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/models" element={<ModelsPage />} />
            <Route path="/models/import" element={<ImportModelPage />} />
            <Route path="/models/:id" element={<ModelDetailPage />} />
            <Route path="/evaluations/:id" element={<EvaluationDetailPage />} />
            <Route path="/evaluations/:id/review" element={<ReviewPage />} />
            <Route path="/reports/:evaluationId" element={<ReportPage />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
