'use client';
import {useEffect,useState} from 'react';
import {Minus,Plus} from 'lucide-react';

export default function CartQuantity({value,min,disabled,lang,onChange}:{value:number;min:number;disabled:boolean;lang:'ar'|'en';onChange:(value:number)=>void}){
  const [draft,setDraft]=useState(String(value));
  useEffect(()=>setDraft(String(value)),[value]);
  const normalized=()=>{
    const parsed=Number(draft);
    return Number.isFinite(parsed)&&draft.trim()!==''?Math.max(min,Math.round(parsed)):min;
  };
  const commit=(next:number)=>{setDraft(String(next));if(next!==value)onChange(next)};
  const t=(ar:string,en:string)=>lang==='ar'?ar:en;
  return <div className="quantity cart-quantity">
    <button type="button" disabled={disabled||normalized()<=min} aria-label={t('تقليل الكمية','Decrease quantity')} onClick={()=>commit(Math.max(min,normalized()-1))}><Minus size={15}/></button>
    <input aria-label={t('الكمية','Quantity')} type="number" inputMode="numeric" min={min} step="1" value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} onBlur={()=>commit(normalized())} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur()}}/>
    <button type="button" disabled={disabled} aria-label={t('زيادة الكمية','Increase quantity')} onClick={()=>commit(normalized()+1)}><Plus size={15}/></button>
  </div>;
}
