import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { DashboardPage } from '../pages/DashboardPage';
import { TrainingSetupPage } from '../pages/TrainingSetupPage';
import { TrainingPage } from '../pages/TrainingPage';
import { ReportPage } from '../pages/ReportPage';
import { HistoryPage } from '../pages/HistoryPage';
import { AnalyticsPage } from '../pages/AnalyticsPage';
import { SystemPage } from '../pages/SystemPage';

/** 应用路由：默认进入登录页，登录后跳转工作台 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/training/setup" element={<TrainingSetupPage />} />
        <Route path="/training/:id" element={<TrainingPage />} />
        <Route path="/report/:id" element={<ReportPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}