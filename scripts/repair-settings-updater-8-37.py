from pathlib import Path

p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')

# 8.32+ already changed checkAndInstall to carry stage progress. 8.37's
# remote-binary patch used to expect the pre-8.32 literal block and therefore
# aborted. Normalize only the updater surface to a deterministic bridge first.
fn_start=s.find('  const checkAndInstall=async()=>{')
fn_end=s.find('  const cleanDuplicates=async()=>{',fn_start)
if fn_start<0 or fn_end<0:
    raise SystemExit('8.37 settings repair: checkAndInstall/cleanDuplicates boundary missing')
legacy_fn='''  const checkAndInstall=async()=>{\n    if(busy)return;setBusy(true);setUpdateProgress(null);\n    try{const u=await api.checkUpdate();setUpdate(u||{none:true});if(u?.version&&u?.install){setUpdateProgress(0);await u.install((p:number)=>setUpdateProgress(p));}}\n    catch(e){setUpdateProgress(null);setUpdate({error:String(e)});await api.showError(`Не удалось обновить ENDLUME: ${String(e)}`)}finally{setBusy(false)}\n  };\n'''
s=s[:fn_start]+legacy_fn+s[fn_end:]

updates_start=s.find("    {tab==='updates'&&")
about_start=s.find("    {tab==='about'&&",updates_start)
if updates_start<0 or about_start<0:
    raise SystemExit('8.37 settings repair: updates/about boundary missing')
legacy_updates='''    {tab==='updates'&&<div className="settingsCard"><h3>Обновления</h3><p>ENDLUME Studio 1.0.0-alpha.8.36</p><p className="settingsNote">Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.</p><button className="settingsAction" disabled={busy} onClick={checkAndInstall}>{busy?(updateProgress!==null?`ОБНОВЛЯЮ ${updateProgress.toFixed(0)}%`:'ПРОВЕРЯЮ…'):'ПРОВЕРИТЬ И ОБНОВИТЬ'}</button>{updateProgress!==null&&<div className="updateProgress"><i style={{width:`${updateProgress}%`}}/><span>{updateProgress.toFixed(0)}%</span></div>}{update?.none&&<div><p className="updateOk">Установлена актуальная alpha-версия: {update.current||'1.0.0-alpha.8.36'}.</p></div>}{update?.version&&<div className="updateFound"><b>Устанавливается ENDLUME {update.version}</b>{update.date&&<small>{String(update.date)}</small>}<p>{update.body}</p><p className="settingsNote">Обновляется только /Applications/ENDLUME Studio.app. После установки приложение автоматически перезапустится.</p></div>}{update?.error&&<p className="updateError">Ошибка обновления: {update.error}</p>}\n      <div className="whatsNew"><h4>SINGLE APP GUARD</h4><p className={appHealthy?'updateOk':'settingsNote'}>{appGuard?.supported===false?'На этой системе не требуется.':appHealthy?'✓ Одна установка: /Applications/ENDLUME Studio.app. Клоны будут удаляться автоматически.':appGuard?.canonicalInstall===false?`ENDLUME запущена не из канонического места. Нужно: /Applications/ENDLUME Studio.app.`:appGuard?`Найдено копий: ${appGuard.remaining?.length||appGuard.found?.length||0}. Текущая: ${appGuard.currentPath||'—'}`:'Проверяю приложения…'}</p>{appGuard?.supported!==false&&appGuard?.canonicalInstall===false&&<button className="settingsAction" disabled={busy} onClick={normalizeName}>ЗАКРЕПИТЬ В /APPLICATIONS КАК ENDLUME STUDIO</button>}{appGuard?.supported!==false&&!appGuard?.singleApp&&<button className="settingsAction" disabled={busy} onClick={cleanDuplicates}>УДАЛИТЬ КЛОНЫ ENDLUME</button>}{appGuard?.currentPath&&<p className="settingsNote">Текущее приложение: {appGuard.currentPath}</p>}<ReleaseHistory/></div></div>}\n'''
s=s[:updates_start]+legacy_updates+s[about_start:]

# The 8.32-only stage state can remain; it is harmless and avoids touching the
# giant state declaration. The 8.37 patch will create checkUpdate/installUpdate.
for marker in [
    'const checkAndInstall=async()=>{',
    'Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac.',
    "onClick={checkAndInstall}>{busy?(updateProgress!==null?`ОБНОВЛЯЮ ${updateProgress.toFixed(0)}%`:'ПРОВЕРЯЮ…'):'ПРОВЕРИТЬ И ОБНОВИТЬ'}",
    '<b>Устанавливается ENDLUME {update.version}</b>',
]:
    if marker not in s:
        raise SystemExit(f'8.37 settings repair incomplete: {marker}')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.37 Settings updater bridge normalized')
