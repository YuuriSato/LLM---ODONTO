import { Bot, CheckCircle2, Pencil } from 'lucide-react';
import { useState } from 'react';
import { api } from '../api/client';
import { FilePicker } from '../components/FilePicker';
import { PageHeader } from '../components/PageHeader';

export function CalibrationPage() {
  const [image, setImage] = useState<File | null>(null);
  const [original, setOriginal] = useState<File | null>(null);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const calibrate = async (label: string) => {
    if (!image) { setStatus('Selecione uma imagem antes de registrar a calibração.'); return; }
    if (!window.confirm('Confirmar o registro desta imagem na calibração local de desenvolvimento?')) return;
    setBusy(true);
    setStatus('Registrando exemplo local...');
    try {
      await api.calibrate(image, original, label);
      setStatus('Exemplo registrado na calibração local. Esta ação não altera os pesos do modelo.');
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : 'Não foi possível registrar o exemplo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page" data-page-panel="calibration">
      <PageHeader eyebrow="Somente desenvolvimento" title="Calibração" description="Registre exemplos locais para avaliação. Este recurso não treina nem altera os pesos dos modelos." />
      <section className="panel calibration-panel">
        <div className="upload-fields">
          <FilePicker id="calibrationImage" label="Imagem do exemplo" hint="Imagem que receberá o rótulo informado." file={image} onChange={setImage} disabled={busy} removeLabel="Remover exemplo de calibração" />
          <FilePicker id="calibrationOriginal" label="Referência opcional" hint="Imagem original usada apenas para comparação." file={original} onChange={setOriginal} disabled={busy} removeLabel="Remover referência de calibração" />
        </div>
        <div className="calibration-actions">
          <button id="markReal" type="button" className="secondary-button" onClick={() => void calibrate('REAL')} disabled={busy}><CheckCircle2 aria-hidden="true" size={18} />Real</button>
          <button id="markModified" type="button" className="secondary-button" onClick={() => void calibrate('MODIFICADO')} disabled={busy}><Pencil aria-hidden="true" size={18} />Modificada</button>
          <button id="markAi" type="button" className="secondary-button" onClick={() => void calibrate('IA_GERADA_EDITADA')} disabled={busy}><Bot aria-hidden="true" size={18} />Gerada ou editada por IA</button>
        </div>
        <p id="calibrationStatus" className="message" role="status">{status}</p>
      </section>
    </div>
  );
}
