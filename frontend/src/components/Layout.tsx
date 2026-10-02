import { BarChart3, History, Menu, Microscope, Settings, SlidersHorizontal, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import type { PageName } from '../types';

const items: { page: PageName; label: string; icon: typeof BarChart3; development?: boolean }[] = [
  { page: 'dashboard', label: 'Painel', icon: BarChart3 },
  { page: 'analyze', label: 'Analisar imagem', icon: Microscope },
  { page: 'history', label: 'Histórico', icon: History },
  { page: 'calibration', label: 'Calibração', icon: SlidersHorizontal, development: true },
  { page: 'settings', label: 'Configurações', icon: Settings },
];

export function Layout({ page, onNavigate, developmentMode, children }: {
  page: PageName;
  onNavigate: (page: PageName) => void;
  developmentMode: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const navigate = (target: PageName) => { onNavigate(target); setOpen(false); };
  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Navegação principal">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">S</div>
          <div><strong>Sato Company</strong><small>Análise de Integridade</small></div>
          <button className="icon-button mobile-close" type="button" onClick={() => setOpen(false)} aria-label="Fechar menu">
            <X aria-hidden="true" size={20} />
          </button>
        </div>
        <nav>
          {items.filter((item) => !item.development || developmentMode).map((item) => (
            <button
              key={item.page}
              type="button"
              data-page={item.page}
              className={page === item.page ? 'active' : ''}
              aria-current={page === item.page ? 'page' : undefined}
              onClick={() => navigate(item.page)}
            >
              <item.icon aria-hidden="true" size={19} />
              <span>{item.label}</span>
              {item.development && <small>DEV</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="product-dot" aria-hidden="true" />
          <div><strong>Serviço local</strong><small>Dados mantidos neste computador</small></div>
        </div>
      </aside>
      {open && <button className="sidebar-backdrop" type="button" aria-label="Fechar menu" onClick={() => setOpen(false)} />}
      <div className="workspace">
        <header className="topbar">
          <button className="icon-button menu-button" type="button" onClick={() => setOpen(true)} aria-label="Abrir menu">
            <Menu aria-hidden="true" size={21} />
          </button>
          <div><strong>Sato Company</strong><span>Análise de imagens odontológicas</span></div>
          {developmentMode && <span className="environment-badge">Modo de desenvolvimento</span>}
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
