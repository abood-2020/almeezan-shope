'use client';
import {useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent} from 'react';
import {createPortal} from 'react-dom';
import {Check, ChevronDown, ChevronLeft, ChevronRight, Search} from 'lucide-react';

export type PickerCategory = {id: number; ar: string; en: string; parentId?: number | null; level?: number};

type Props = {
  categories: PickerCategory[];
  value: number | null;
  onChange: (id: number | null) => void;
  en: boolean;
  label: string;
  allowEmpty?: boolean;
  emptyLabel?: string;
  disabledReason?: (category: PickerCategory) => string | null;
  loading?: boolean;
  error?: string;
  trail?: boolean;
  showId?: boolean;
};

type Row = PickerCategory & {depth: number; path: string; names: string[]; hasChildren: boolean};
type PanelBox = {top: number; left: number; width: number; maxHeight: number};

export function CategoryTrail({names, en}: {names: string[]; en: boolean}) {
  const parts = names.filter(Boolean);
  if (!parts.length) return null;
  const Sep = en ? ChevronRight : ChevronLeft;
  return <span className="category-trail">
    {parts.map((name, index) => <span key={`${name}-${index}`} className="category-trail-step">
      {index > 0 && <Sep className="category-trail-sep" size={13} aria-hidden="true"/>}
      <span className={index === parts.length - 1 ? 'category-trail-leaf' : 'category-trail-parent'}>{name}</span>
    </span>)}
  </span>;
}

export default function CategoryPicker({categories, value, onChange, en, label, allowEmpty, emptyLabel, disabledReason, loading, error, trail, showId}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [active, setActive] = useState(0);
  const [box, setBox] = useState<PanelBox | null>(null);
  const tree = useMemo(() => buildRows(categories, en, showId), [categories, en, showId]);
  const byId = useMemo(() => new Map(tree.map(row => [row.id, row])), [tree]);
  const selected = value == null ? null : byId.get(value) || categories.find(category => category.id === value) || null;
  const searching = query.trim().length > 0;
  const visible = useMemo(() => {
    if (searching) {
      const needle = query.trim().toLowerCase();
      return tree.filter(row => row.ar.toLowerCase().includes(needle) || row.en.toLowerCase().includes(needle) || row.path.toLowerCase().includes(needle));
    }
    return tree.filter(row => {
      let parent = row.parentId ?? null;
      const seen = new Set<number>();
      while (parent && !seen.has(parent)) {
        if (!expanded.has(parent)) return false;
        seen.add(parent);
        parent = byId.get(parent)?.parentId ?? null;
      }
      return true;
    });
  }, [tree, searching, query, expanded, byId]);
  const options = allowEmpty ? [null, ...visible] : visible;

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      const gap = 4;
      const margin = 8;
      const limit = 250;
      const below = window.innerHeight - rect.bottom - gap - margin;
      const above = rect.top - gap - margin;
      const dropUp = below < 160 && above > below;
      const maxHeight = Math.max(120, Math.min(limit, dropUp ? above : below));
      const width = Math.min(rect.width, window.innerWidth - margin * 2);
      const left = Math.min(Math.max(margin, rect.left), window.innerWidth - width - margin);
      const top = dropUp ? Math.max(margin, rect.top - gap - maxHeight) : rect.bottom + gap;
      setBox({top, left, width, maxHeight});
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onEscape, true);
    searchRef.current?.focus();
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onEscape, true);
    };
  }, [open, box]);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({block: 'nearest'});
  }, [active, open, visible.length]);

  const choose = (id: number | null) => {
    if (id != null) {
      const category = byId.get(id);
      if (category && disabledReason?.(category)) return;
    }
    onChange(id);
    setOpen(false);
    setQuery('');
  };
  const onKey = (event: KeyboardEvent) => {
    if (!open && (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(index => {
        const next = event.key === 'ArrowDown' ? index + 1 : index - 1;
        return (next + options.length) % Math.max(options.length, 1);
      });
      return;
    }
    if (event.key === 'Home') {event.preventDefault(); setActive(0); return;}
    if (event.key === 'End') {event.preventDefault(); setActive(Math.max(options.length - 1, 0)); return;}
    const current = options[active];
    const expandKey = en ? 'ArrowRight' : 'ArrowLeft';
    const collapseKey = en ? 'ArrowLeft' : 'ArrowRight';
    if (event.key === expandKey && current && 'id' in current && current.hasChildren && !searching) {
      event.preventDefault();
      setExpanded(values => new Set(values).add(current.id));
    }
    if (event.key === collapseKey && current && 'id' in current && !searching) {
      event.preventDefault();
      setExpanded(values => {
        const next = new Set(values);
        if (current.hasChildren && next.has(current.id)) next.delete(current.id);
        else if (current.parentId) next.delete(current.parentId);
        return next;
      });
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (current === null) choose(null);
      else if (current) choose(current.id);
    }
  };

  const baseName = selected ? (en ? selected.en : selected.ar) : '';
  const selectedPath = selected ? ('path' in selected ? selected.path : (showId && selected.id ? `${selected.id} — ${baseName}` : baseName)) : '';
  const selectedNames = selected && 'names' in selected && selected.names.length ? selected.names : (selectedPath ? selectedPath.split(' / ') : []);
  const panel = open && box && typeof document !== 'undefined' ? createPortal(
    <div ref={panelRef} className="category-picker-panel" dir={en ? 'ltr' : 'rtl'} style={{top: box.top, left: box.left, width: box.width, maxHeight: box.maxHeight}}>
      <label className="category-picker-search">
        <Search size={14}/>
        <input ref={searchRef} value={query} placeholder={t('بحث', 'Search')} aria-label={t('بحث في التصنيفات', 'Search categories')} onChange={event => {setQuery(event.target.value); setActive(0);}} onKeyDown={onKey}/>
      </label>
      <div id={listId} role="listbox" aria-label={label} className="category-picker-options" tabIndex={-1}>
        {loading && <p className="category-picker-state">{t('جارٍ تحميل التصنيفات…', 'Loading categories…')}</p>}
        {!loading && error && <p className="category-picker-state error" role="alert">{error}</p>}
        {!loading && !error && allowEmpty && <button type="button" role="option" aria-selected={value == null} data-active={active === 0} className={'category-picker-option' + (active === 0 ? ' active' : '') + (value == null ? ' selected' : '')} onMouseEnter={() => setActive(0)} onClick={() => choose(null)}>
          <span className="category-picker-copy"><strong>{emptyLabel || t('قسم رئيسي — بلا أب', 'Main category — no parent')}</strong></span>
          {value == null && <Check size={14}/>}
        </button>}
        {!loading && !error && !visible.length && <p className="category-picker-state">{categories.length ? t('لا توجد تصنيفات مطابقة', 'No matching categories') : t('لا توجد تصنيفات بعد', 'No categories yet')}</p>}
        {!loading && !error && visible.map((row, index) => {
          const optionIndex = allowEmpty ? index + 1 : index;
          const reason = disabledReason?.(row) || '';
          const Chevron = en ? ChevronRight : ChevronLeft;
          const baseName = en ? row.en : row.ar;
          const name = showId && row.id ? `${row.id} — ${baseName}` : baseName;
          return <div key={row.id} role="option" aria-selected={value === row.id} aria-disabled={!!reason} data-active={active === optionIndex} className={'category-picker-option' + (active === optionIndex ? ' active' : '') + (value === row.id ? ' selected' : '') + (reason ? ' disabled' : '')} style={{paddingInlineStart: searching ? 8 : 8 + row.depth * 12}} onMouseEnter={() => setActive(optionIndex)}>
            {!searching && row.hasChildren ? <button type="button" className={'category-picker-expand' + (expanded.has(row.id) ? ' open' : '')} aria-label={expanded.has(row.id) ? t('طي', 'Collapse') : t('توسيع', 'Expand')} aria-expanded={expanded.has(row.id)} onClick={() => setExpanded(values => {const next = new Set(values); next.has(row.id) ? next.delete(row.id) : next.add(row.id); return next;})}><Chevron size={13}/></button> : <span className="category-picker-expand spacer"/>}
            <button type="button" className="category-picker-choice" disabled={!!reason} onClick={() => choose(row.id)}>
              <span className="category-picker-copy">
                <strong>{name}</strong>
                {(searching || row.depth > 0) && <small>{row.path}</small>}
                {reason && <small>{reason}</small>}
              </span>
              {value === row.id && <Check size={14}/>}
            </button>
          </div>;
        })}
      </div>
    </div>,
    document.body,
  ) : null;

  const placeholder = allowEmpty ? (emptyLabel || t('قسم رئيسي — بلا أب', 'Main category — no parent')) : t('اختر تصنيفًا', 'Choose a category');
  return <div className={'category-picker' + (open ? ' open' : '') + (trail ? ' trail' : '')} ref={rootRef} dir={en ? 'ltr' : 'rtl'}>
    <span className="field-label" id={`${listId}-label`}>{label}</span>
    <button type="button" className="category-picker-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} aria-labelledby={`${listId}-label`} onClick={() => setOpen(value => !value)} onKeyDown={onKey}>
      {selected && trail ? <CategoryTrail names={selectedNames} en={en}/> : <span>{selected ? selectedPath : placeholder}</span>}
      <ChevronDown size={15}/>
    </button>
    {panel}
  </div>;
}

function buildRows(categories: PickerCategory[], en: boolean, showId?: boolean): Row[] {
  const children = new Map<number | null, PickerCategory[]>();
  categories.forEach(category => {
    const parent = category.parentId ?? null;
    children.set(parent, [...(children.get(parent) || []), category]);
  });
  const rows: Row[] = [];
  const walk = (parent: number | null, depth: number, trail: string[]) => {
    (children.get(parent) || []).forEach(category => {
      const baseName = en ? category.en : category.ar;
      const name = showId && category.id ? `${category.id} — ${baseName}` : baseName;
      const names = [...trail, name];
      const path = names.join(' / ');
      const nested = children.get(category.id) || [];
      rows.push({...category, depth, path, names, hasChildren: nested.length > 0});
      if (depth < 2) walk(category.id, depth + 1, names);
    });
  };
  walk(null, 0, []);
  const seen = new Set(rows.map(row => row.id));
  categories.filter(category => !seen.has(category.id)).forEach(category => {
    const baseName = en ? category.en : category.ar;
    const name = showId && category.id ? `${category.id} — ${baseName}` : baseName;
    rows.push({...category, depth: Math.max((category.level || 1) - 1, 0), path: name, names: [name], hasChildren: false});
  });
  return rows;
}
