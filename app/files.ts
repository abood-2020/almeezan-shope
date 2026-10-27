import {productImageForOption,statuses,type Order,type Product} from './data';
import {fillProductTemplate,importLanguage,inspectProductImport,productTemplateColumns,type ImportLang} from './product-import';

function safeCell(value: unknown) {
  if (typeof value !== 'string') return value;
  return /^[=+\-@]/.test(value.trim()) ? `'${value}` : value;
}

export async function exportExcel(rows: Record<string, unknown>[], name: string, options?: {sheet?: string; rtl?: boolean}) {
  const XLSX = await import('xlsx');
  const safe = rows.map(row => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, safeCell(value)])));
  const ws = XLSX.utils.json_to_sheet(safe);
  ws['!cols'] = Object.keys(safe[0] || {}).map(() => ({wch: 24}));
  if (options && ws['!ref']) {
    ws['!autofilter'] = {ref: ws['!ref']};
    ws['!views'] = [{state: 'frozen', xSplit: 0, ySplit: 1, topLeftCell: 'A2', activePane: 'bottomLeft'}];
  }
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, (options?.sheet || 'Data').slice(0, 31));
  if (options?.rtl) wb.Workbook = {Views: [{RTL: true}]};
  XLSX.writeFile(wb, `${name}.xlsx`);
}

export async function downloadAdminExcel(tab: string, rows: any[], lang: 'ar' | 'en') {
  const english = lang === 'en';
  const label = (ar: string, en: string) => english ? en : ar;
  let sheet = 'Data';
  let mapped: Record<string, unknown>[] = [];
  if (tab === 'orders') {
    sheet = label('الطلبات', 'Orders');
    mapped = rows.map(row => ({
      [label('رقم الطلب', 'Order Number')]: row.id,
      [label('تاريخ الطلب', 'Order Date')]: row.date,
      [label('حالة الطلب', 'Order Status')]: (english ? statuses[row.status]?.en : statuses[row.status]?.ar) || row.status,
      [label('اسم التاجر', 'Trader Name')]: row.merchant,
      [label('العملة', 'Currency')]: row.currency,
      [label('الملاحظات', 'Notes')]: row.note || '',
      [label('إجمالي الطلب', 'Order Total')]: row.total,
      [label('عدد البنود', 'Line count')]: Array.isArray(row.items) ? row.items.length : 0,
    }));
  } else if (tab === 'invoices') {
    sheet = label('الفواتير', 'Invoices');
    mapped = rows.map(row => ({
      [label('رقم الفاتورة', 'Invoice Number')]: row.id,
      [label('تاريخ الفاتورة', 'Invoice Date')]: row.date,
      [label('التاجر', 'Trader')]: row.merchant,
      [label('القيمة المسجلة', 'Recorded amount')]: row.amount,
      [label('اسم الملف', 'File name')]: row.name || '',
    }));
  } else if (tab === 'products') {
    sheet = label('المنتجات', 'Products');
    mapped = rows.map(row => ({
      [label('كود المنتج', 'Product Code')]: String(row.code ?? ''),
      [label('كود المصنع', 'Factory Code')]: String(row.factory_code ?? ''),
      [label('اسم المنتج', 'Product Name')]: english ? row.en : row.ar,
      [label('الاسم بالعربية', 'Arabic name')]: row.ar,
      [label('الاسم بالإنجليزية', 'English name')]: row.en,
      [label('التصنيف', 'Category')]: row.category || '',
      [label('وحدة البيع', 'Unit')]: row.unit || '',
      [label('الحد الأدنى', 'Minimum')]: row.min,
      [label('متوفر', 'Available')]: row.available ? 1 : 0,
      [label('السعر الأساسي', 'Base Price')]: row.price,
    }));
  } else if (tab === 'merchants') {
    sheet = label('التجار', 'Traders');
    mapped = rows.map(row => ({
      [label('المعرف', 'ID')]: row.id,
      [label('اسم التاجر', 'Trader Name')]: english ? row.en : row.ar,
      [label('الاسم بالعربية', 'Arabic name')]: row.ar,
      [label('الاسم بالإنجليزية', 'English name')]: row.en,
      [label('اسم المستخدم', 'Username')]: row.username,
      [label('البريد الإلكتروني', 'Email')]: row.email,
      [label('قائمة الأسعار', 'Price List')]: row.list,
      [label('نشط', 'Active')]: row.active ? 1 : 0,
    }));
  }
  await exportExcel(mapped, `Algharabli-${tab}`, {sheet, rtl: !english});
}
export const columns = productTemplateColumns;
export async function downloadTemplate(lang: ImportLang = 'ar', sampleCategoryId?: number) {
  const XLSX = await import('xlsx');
  XLSX.writeFile(fillProductTemplate(XLSX, importLanguage(lang), sampleCategoryId), 'Algharabli-Product-Template.xlsx');
}
export async function readImport(file: File, products: Product[], categoryIds: number[] = [], lang: ImportLang = 'ar') {
  const XLSX = await import('xlsx');
  const book = XLSX.read(await file.arrayBuffer());
  const sheet = book.Sheets[book.SheetNames[0]];
  const matrix = XLSX.utils.sheet_to_json(sheet, {header: 1, raw: true}) as unknown[][];
  return inspectProductImport(matrix, products.map(product => product.code), categoryIds, importLanguage(lang));
}
export async function downloadOrder(o:Order,products:Product[],lang:string,email:string,brand?:{nameAr:string;nameEn:string}){const {jsPDF}=await import('jspdf');await document.fonts.ready;const en=lang==='en';const brandAr=brand?.nameAr||'رِواق';const brandEn=brand?.nameEn||'Riwaq';const c=document.createElement('canvas');c.width=1240;c.height=1754;const g=c.getContext('2d')!;const pdf=new jsPDF({unit:'mm',format:'a4'});let page=0,y=0;const text=(s:string,x:number,y:number,size=25,align:CanvasTextAlign='right',color='#263238')=>{g.font=`${size>=30?'700':'400'} ${size}px Cairo`;g.fillStyle=color;g.textAlign=align;g.direction=align==='right'?'rtl':'ltr';g.fillText(s,x,y)};const header=()=>{g.fillStyle='#fff';g.fillRect(0,0,1240,1754);g.fillStyle='#142B3B';g.fillRect(0,0,1240,165);text(en?brandEn+' | ORDER REQUEST':brandAr+' | طلب تجاري',1170,85,42,'right','#ffffff');text(o.id,70,135,20,'left','#c8d9d9');text(en?'Trader: '+(o.merchant==='متجر الأفق'?'Horizon Store':'Atlas Trading'):'التاجر: '+o.merchant,1170,225,28);text(email,1170,267,23);text(o.date,70,225,25,'left');text(en?'Commercial request · not an accounting invoice':'طلب للمتابعة التجارية · ليس فاتورة محاسبية',1170,322,22,'right','#778579');g.fillStyle='#edf3ef';g.fillRect(55,350,1130,62);text(en?'Products, options and quantities':'الأصناف والخيارات والكميات',1160,391,24);y=440};const finish=()=>{text(en?brandEn:brandAr,620,1690,20,'center','#7b8882');pdf.addImage(c.toDataURL('image/jpeg',.92),'JPEG',0,0,210,297)};header();for(const l of o.items){if(y>1370){finish();pdf.addPage();page++;header()}const p=products.find(p=>p.id===l.id);if(!p)continue;const img=new Image();img.src=productImageForOption(p,l.option);await new Promise<void>(resolve=>{img.onload=()=>resolve();img.onerror=()=>resolve()});if(img.naturalWidth){const ratio=Math.min(125/img.width,125/img.height);g.drawImage(img,1040+(125-img.width*ratio)/2,y,img.width*ratio,img.height*ratio)}text(en?p.en:p.ar,1000,y+30,27);text(p.code,1000,y+69,21);text((en?(l.option.split(' · ')[0].split(' / ')[1]||l.option.split(' · ')[0]):l.option.split(' · ')[0].split(' / ')[0])+(l.option.includes(' · ')?' · '+l.option.split(' · ')[1]:''),1000,y+110,20);text(`${l.qty} × ${l.price.toFixed(2)} ${o.currency}`,520,y+69,25);text(`${(l.qty*l.price).toFixed(2)} ${o.currency}`,85,y+69,27,'left','#B41F71');g.strokeStyle='#e4e9e3';g.beginPath();g.moveTo(70,y+150);g.lineTo(1170,y+150);g.stroke();y+=178}if(y>1310){finish();pdf.addPage();page++;header()}text(en?'TOTAL':'الإجمالي',1160,y+50,33);text(`${o.total.toFixed(2)} ${o.currency}`,80,y+50,33,'left','#B41F71');if(o.note){const words=o.note.split(' ');let line='',ty=y+120;for(const word of words){if(g.measureText(line+' '+word).width>1060){text(line,1160,ty,22);ty+=36;line=word}else line+=(line?' ':'')+word}if(line)text(line,1160,ty,22)}finish();pdf.save(o.id+'.pdf')}
