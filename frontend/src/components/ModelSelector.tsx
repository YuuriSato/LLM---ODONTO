import { RefreshCw } from 'lucide-react';
import type { SelectedModel } from '../types';

export function ModelSelector({ models, value, loading, error, onChange, onRefresh, disabled }: {
  models: SelectedModel[];
  value: string;
  loading: boolean;
  error: string;
  onChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  disabled?: boolean;
}) {
  const selected = models.find((item) => item.value === value);
  return (
    <div className="field model-field">
      <div className="field-label-row">
        <label htmlFor="modelSelect">Modelo de análise</label>
        {selected?.experimental && <span className="status-badge warning">Experimental</span>}
      </div>
      <div className="select-row">
        <select
          id="modelSelect"
          value={value}
          disabled={disabled || loading || !models.length}
          onChange={(event) => onChange(event.target.value)}
          required
        >
          {!models.length && <option value="">{loading ? 'Carregando modelos...' : 'Nenhum modelo disponível'}</option>}
          {models.map((model) => (
            <option key={model.value} value={model.value} disabled={!model.available}>{model.label}</option>
          ))}
        </select>
        <button
          id="refreshModels"
          type="button"
          className="icon-button"
          onClick={() => void onRefresh()}
          disabled={loading || disabled}
          aria-label="Atualizar modelos"
          title="Atualizar modelos"
        >
          <RefreshCw aria-hidden="true" size={18} className={loading ? 'spin' : ''} />
        </button>
      </div>
      <span id="modelStatus" className={`field-hint ${error || selected?.available === false ? 'error-text' : ''}`} role="status">
        {error || (selected?.available === false ? 'O modelo selecionado está indisponível. Escolha outro ou atualize a lista.' : '')}
      </span>
    </div>
  );
}
