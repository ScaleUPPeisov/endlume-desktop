import React from 'react';
import { useApp } from '../store';
import type { Page } from '../types';
import { Icon,Logo } from './ui';

const tabs:Array<{id:Page;label:string;icon:'project'|'render'|'library'|'settings'}>=[
  {id:'project',label:'Проект',icon:'project'},
  {id:'render',label:'Рендер',icon:'render'},
  {id:'library',label:'Библиотека',icon:'library'},
  {id:'settings',label:'Настройки',icon:'settings'},
];

export function Topbar(){
  const page=useApp(s=>s.page),setPage=useApp(s=>s.setPage),projects=useApp(s=>s.projects);
  const active=projects.filter(p=>p.status==='rendering').length;
  return <div className="topbar">
    <div className="topbarSpacer"/>
    <Logo/>
    <nav className="topnav">{tabs.map(t=><button key={t.id} onClick={()=>setPage(t.id)} className={page===t.id?'active':''}><Icon name={t.icon}/><span>{t.label}</span>{t.id==='render'&&active>0&&<b>{active}</b>}</button>)}</nav>
  </div>
}
