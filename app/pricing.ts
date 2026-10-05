import {initialProducts, type Product} from './data';
export type PriceList={id:string;ar:string;en:string;currency:string;prices:Record<number,number>};
export type PriceDraft={currency:string;values:Record<number,string>};
export const baseCurrency='ILS';
export const initialPriceLists:PriceList[]=[
  {id:'local',ar:'تجار فلسطين',en:'Palestine traders',currency:'ILS',prices:Object.fromEntries(initialProducts.map(p=>[p.id,p.price]))},
  {id:'export',ar:'تجار التصدير',en:'Export traders',currency:'USD',prices:{1:25,2:14,3:47,4:34,5:23,6:30,7:27,8:22}},
];
// An absent price never converts a base amount into another currency.
export function effectivePrice(product:Product,list:PriceList):number{
  const assigned=list.prices[product.id];
  return Number.isFinite(assigned)?assigned:list.currency===baseCurrency?product.price:NaN;
}
export function commitPrices(values:Record<number,string>):Record<number,number>{
  const result:Record<number,number>={};
  for(const [id,raw] of Object.entries(values)){
    if(raw.trim()==='')continue;
    const value=Number(raw);
    if(!Number.isFinite(value)||value<0)throw new Error('Invalid price');
    result[Number(id)]=Math.round((value+Number.EPSILON)*100)/100;
  }
  return result;
}
