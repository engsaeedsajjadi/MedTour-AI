'use client';
import {useEffect,useRef,useState} from 'react';
import {PART_HELP,helpEnabled} from '@/lib/help';

/**
 * While help is on: marks the parts of the current page that have help text and shows that text
 * in a small card beside the pointer (or beside the focused element, for keyboard users).
 */
export default function HelpLayer({section}:{section:string}){
 const [on,setOn]=useState(false);
 const [tip,setTip]=useState<{text:string;x:number;y:number}|null>(null);
 const timer=useRef<number|undefined>(undefined);

 useEffect(()=>{const sync=()=>setOn(helpEnabled());sync();window.addEventListener('medtour-help',sync);return()=>window.removeEventListener('medtour-help',sync);},[]);

 // Attach help text to page parts (headings are matched by their words, so pages need no changes).
 useEffect(()=>{
  if(!on){document.querySelectorAll('[data-help-auto]').forEach(el=>{el.removeAttribute('data-help');el.removeAttribute('data-help-auto');});return;}
  const page=section.split('/')[0];
  const apply=()=>{
   const main=document.getElementById('main-content');if(!main)return;
   for(const rule of PART_HELP){
    if(rule.path!=='*'&&rule.path!==page)continue;
    let targets:Element[]=[];
    if(rule.selector)targets=[...main.querySelectorAll(rule.selector)];
    if(rule.heading)targets=[...main.querySelectorAll('h2')].filter(h=>(h.textContent||'').includes(rule.heading||'')).map(h=>h.closest('section')||h);
    for(const el of targets){if(!el.hasAttribute('data-help')){el.setAttribute('data-help',rule.text);el.setAttribute('data-help-auto','1');}}
   }
  };
  apply();
  const observer=new MutationObserver(()=>{window.clearTimeout(timer.current);timer.current=window.setTimeout(apply,150);});
  const main=document.getElementById('main-content');if(main)observer.observe(main,{childList:true,subtree:true});
  return()=>{observer.disconnect();window.clearTimeout(timer.current);};
 },[on,section]);

 // Show the closest help text under the pointer or the keyboard focus.
 useEffect(()=>{
  if(!on){setTip(null);return;}
  const show=(target:EventTarget|null,x:number,y:number)=>{
   const el=target instanceof Element?target.closest('[data-help]'):null;
   const text=el?.getAttribute('data-help');
   setTip(text?{text,x,y}:null);
  };
  const move=(e:MouseEvent)=>show(e.target,e.clientX,e.clientY);
  const focus=(e:FocusEvent)=>{const r=(e.target as Element)?.getBoundingClientRect?.();if(r)show(e.target,r.left,r.bottom);};
  const leave=()=>setTip(null);
  document.addEventListener('mousemove',move);document.addEventListener('focusin',focus);document.addEventListener('mouseleave',leave);
  return()=>{document.removeEventListener('mousemove',move);document.removeEventListener('focusin',focus);document.removeEventListener('mouseleave',leave);};
 },[on]);

 if(!on||!tip)return null;
 const w=300,left=Math.max(12,Math.min(tip.x-w+16,(typeof window!=='undefined'?window.innerWidth:1200)-w-12));
 const below=typeof window==='undefined'||tip.y+160<window.innerHeight;
 return <div className="helpTip" role="tooltip" style={{left,top:below?tip.y+18:undefined,bottom:below?undefined:(window.innerHeight-tip.y)+14,width:w}}>
  <span className="helpTipIcon" aria-hidden="true">؟</span>{tip.text}
 </div>;
}
