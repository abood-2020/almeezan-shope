import type {Product} from './data';

// Product types are inferred from actual item names; absent types never create links.
const productTypes = [
  {id:'tees',ar:'تيشيرتات',en:'T-shirts',match:/تيشيرت|تي.?شرت|\btee\b|t-shirt/i},
  {id:'shirts',ar:'قمصان',en:'Shirts',match:/قميص|قمصان|\bshirt\b/i},
  {id:'trousers',ar:'بناطيل',en:'Trousers',match:/بنطال|بناطيل|trousers|pants/i},
  {id:'blazers',ar:'بليزرات',en:'Blazers',match:/بليزر|blazer/i},
  {id:'dresses',ar:'فساتين',en:'Dresses',match:/فستان|فساتين|dress/i},
  {id:'sets',ar:'أطقم',en:'Sets',match:/طقم|أطقم|\bset\b/i},
  {id:'cardigans',ar:'كارديغان',en:'Cardigans',match:/كارديغان|cardigan/i},
];
export type CatalogGroup={id:number;ar:string;en:string;count:number;children:{id:string;ar:string;en:string;count:number}[]};
export const productType=(p:Product)=>productTypes.find(type=>type.match.test(p.ar+' '+p.en));
export function catalogGroups(categories:{ar:string;en:string}[],products:Product[]):CatalogGroup[]{
  return categories.slice(1).map((c,i)=>{
    const items=products.filter(p=>p.cat===i+1);
    return {...c,id:i+1,count:items.length,children:productTypes.flatMap(type=>{
      const count=items.filter(p=>productType(p)?.id===type.id).length;
      return count?[{id:type.id,ar:type.ar,en:type.en,count}]:[];
    })};
  });
}
export const catalogHref=(category=0,subcategory='')=>{
  const params=new URLSearchParams();
  if(category)params.set('category',String(category));
  if(subcategory)params.set('subcategory',subcategory);
  return '#products'+(params.size?'?'+params.toString():'');
};
export function readStoreRoute(hash:string,groups:CatalogGroup[]){
  const [raw,search='']=hash.replace(/^#/,'').split('?');
  const page=['home','products','cart','portal','admin','confirmation','info','traders','export','contact'].includes(raw)?raw:'home';
  const params=new URLSearchParams(search);
  const candidate=Number(params.get('category')||0);
  const group=groups.find(g=>g.id===candidate);
  const category=group?candidate:0;
  const requested=params.get('subcategory')||'';
  const subcategory=group?.children.some(c=>c.id===requested)?requested:'';
  return {page,category,subcategory};
}
