import { useState } from 'react';
import { Layout } from './components/Layout';
import { useModelCatalog } from './hooks/useModelCatalog';
import { AnalyzePage } from './pages/AnalyzePage';
import { CalibrationPage } from './pages/CalibrationPage';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { SettingsPage } from './pages/SettingsPage';
import type { PageName } from './types';

export function App() {
  const [page, setPage] = useState<PageName>('analyze');
  const [showFullEvidence, setShowFullEvidenceState] = useState(() => localStorage.getItem('perito.showFullEvidence') === '1');
  const models = useModelCatalog();
  const setShowFullEvidence = (value: boolean) => {
    localStorage.setItem('perito.showFullEvidence', value ? '1' : '0');
    setShowFullEvidenceState(value);
  };

  return (
    <Layout page={page} onNavigate={setPage} developmentMode={Boolean(models.catalog?.development_mode)}>
      {page === 'dashboard' && <DashboardPage agents={models.agents} agentsLoading={models.loading} />}
      {page === 'analyze' && (
        <AnalyzePage
          models={models.models}
          selected={models.selected}
          selectedValue={models.selectedValue}
          catalogLoading={models.loading}
          catalogError={models.error}
          setSelectedValue={models.setSelectedValue}
          refreshModels={models.refresh}
          showFullEvidence={showFullEvidence}
        />
      )}
      {page === 'history' && <HistoryPage />}
      {page === 'calibration' && models.catalog?.development_mode && <CalibrationPage />}
      {page === 'settings' && (
        <SettingsPage
          showFullEvidence={showFullEvidence}
          setShowFullEvidence={setShowFullEvidence}
          agents={models.agents}
          catalog={models.catalog}
          loading={models.loading}
          error={models.error}
        />
      )}
    </Layout>
  );
}
