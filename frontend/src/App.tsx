import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import RequireAuth from "./auth/RequireAuth";
import CreateAccountPage from "./pages/CreateAccountPage";
import CreateEvaluationPage from "./pages/CreateEvaluationPage";
import DocumentationPage from "./pages/DocumentationPage";
import EvaluationDetailPage from "./pages/EvaluationDetailPage";
import EvaluationsHistoryPage from "./pages/EvaluationsHistoryPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ImportModelPage from "./pages/ImportModelPage";
import LeaderboardPage from "./pages/LeaderboardPage";
import LoginPage from "./pages/LoginPage";
import ModelDetailPage from "./pages/ModelDetailPage";
import ModelsPage from "./pages/ModelsPage";
import OverviewPage from "./pages/OverviewPage";
import ReportPage from "./pages/ReportPage";
import ReviewPage from "./pages/ReviewPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/create-account" element={<CreateAccountPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/models" element={<ModelsPage />} />
            <Route path="/models/import" element={<ImportModelPage />} />
            <Route path="/models/:id" element={<ModelDetailPage />} />
            <Route path="/evaluations" element={<EvaluationsHistoryPage />} />
            <Route path="/evaluations/new" element={<CreateEvaluationPage />} />
            <Route path="/evaluations/:id" element={<EvaluationDetailPage />} />
            <Route path="/evaluations/:id/review" element={<ReviewPage />} />
            <Route path="/reports/:evaluationId" element={<ReportPage />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/documentation" element={<DocumentationPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
