import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import CreateEvaluationDraftPage from "./pages/CreateEvaluationDraftPage";
import CreateEvaluationPage from "./pages/CreateEvaluationPage";
import DocumentationPage from "./pages/DocumentationPage";
import EvaluationDetailPage from "./pages/EvaluationDetailPage";
import EvaluationsHistoryPage from "./pages/EvaluationsHistoryPage";
import ImportModelPage from "./pages/ImportModelPage";
import ModelDetailPage from "./pages/ModelDetailPage";
import ModelsPage from "./pages/ModelsPage";
import OverviewPage from "./pages/OverviewPage";
import ReportPage from "./pages/ReportPage";
import ReviewPage from "./pages/ReviewPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/models/import" element={<ImportModelPage />} />
          <Route path="/models/:id" element={<ModelDetailPage />} />
          <Route path="/evaluations" element={<EvaluationsHistoryPage />} />
          <Route path="/evaluations/new" element={<CreateEvaluationDraftPage />} />
          <Route path="/evaluations/new-legacy" element={<CreateEvaluationPage />} />
          <Route path="/evaluations/:id" element={<EvaluationDetailPage />} />
          <Route path="/evaluations/:id/review" element={<ReviewPage />} />
          <Route path="/reports/:evaluationId" element={<ReportPage />} />
          <Route path="/documentation" element={<DocumentationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
