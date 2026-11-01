'use client';
import {useEffect,useState} from 'react';
import {cachedOrganization,loadOrganization} from '@/lib/preferences';

/** Suggestions from the lists defined in Settings (visa authorities or supplier desks), for an input's `list`. */
export default function OrgList({id,kind}:{id:string,kind:'visa_authorities'|'supplier_desks'}){
 const [items,setItems]=useState<string[]>([]);
 useEffect(()=>{const c=cachedOrganization();if(c?.[kind])setItems(c[kind]);
  loadOrganization().then(o=>setItems(o.profile[kind]||[])).catch(()=>{});},[kind]);
 return <datalist id={id}>{items.map(x=><option key={x} value={x}/>)}</datalist>;
}
