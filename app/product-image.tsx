'use client';
import {useEffect,useRef,useState} from 'react';
import {ImageOff} from 'lucide-react';
import {assetSrc,productImageSrc,type Product} from './data';

export default function ProductImage({product,lang,colorIndex=0,eager=false,overrideSrc}:{product:Product;lang:'ar'|'en';colorIndex?:number;eager?:boolean;overrideSrc?:string}){
  const src=overrideSrc?assetSrc(overrideSrc):productImageSrc(product,colorIndex);
  const color=product.colors?.[colorIndex];
  return <ImageFrame key={src} src={src} alt={`${lang==='ar'?product.ar:product.en}${color?' · '+(lang==='ar'?color.ar:color.en):''}`} lang={lang} eager={eager}/>;
}

function ImageFrame({src,alt,lang,eager}:{src:string;alt:string;lang:'ar'|'en';eager:boolean}){
  const [status,setStatus]=useState<'loading'|'ready'|'error'>('loading');
  const imageRef=useRef<HTMLImageElement>(null);
  useEffect(()=>{const image=imageRef.current;if(status==='loading'&&image?.complete)setStatus(image.naturalWidth?'ready':'error')},[src,status]);
  return <span className={'product-image-shell '+status}>
    {status==='loading'&&<span className="image-placeholder" aria-hidden="true"/>}
    {status==='error'?<span className="image-error" role="img" aria-label={lang==='ar'?'الصورة غير متاحة':'Image unavailable'}><ImageOff size={26}/><small>{lang==='ar'?'الصورة غير متاحة':'Image unavailable'}</small></span>:<img ref={imageRef} src={src} alt={alt} loading={eager?'eager':'lazy'} onLoad={()=>setStatus('ready')} onError={()=>setStatus('error')}/>}
  </span>;
}
