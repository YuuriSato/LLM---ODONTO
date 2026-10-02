import { ImagePlus, X } from 'lucide-react';
import { useRef } from 'react';

interface Props {
  id: string;
  label: string;
  hint: string;
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
  required?: boolean;
  removeLabel: string;
}

export function FilePicker({ id, label, hint, file, onChange, disabled, required, removeLabel }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  const clear = () => {
    if (inputRef.current) inputRef.current.value = '';
    onChange(null);
    inputRef.current?.focus();
  };

  return (
    <div className="file-field">
      <label htmlFor={id}>{label}</label>
      <div className={`file-picker ${file ? 'has-file' : ''}`}>
        <ImagePlus aria-hidden="true" size={20} />
        <div className="file-copy">
          <span>{file?.name || 'Selecionar arquivo'}</span>
          <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : hint}</small>
        </div>
        <input
          ref={inputRef}
          id={id}
          name={id === 'originalImage' ? 'original_image' : 'image'}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/bmp"
          required={required}
          disabled={disabled}
          onChange={(event) => onChange(event.target.files?.[0] || null)}
          aria-describedby={`${id}-hint`}
        />
        {file && (
          <button
            type="button"
            className="icon-button remove-photo"
            data-remove-photo={id}
            aria-label={removeLabel}
            title={removeLabel}
            onClick={clear}
            disabled={disabled}
          >
            <X aria-hidden="true" size={18} />
          </button>
        )}
      </div>
      <span id={`${id}-hint`} className="field-hint">{hint}</span>
    </div>
  );
}
