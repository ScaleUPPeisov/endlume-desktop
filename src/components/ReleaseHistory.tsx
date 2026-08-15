import React from 'react';

type Release={version:string;date:string;current?:boolean;title:string;items:string[]};

const releases:Release[]=[
  {version:'1.0.0-alpha.8.12',date:'15.08.2026',current:true,title:'Компактная neon-навигация',items:[
    'Обновлена только верхняя навигация ENDLUME Studio: Проект, Рендер, Библиотека и Настройки стали компактнее и аккуратнее.',
    'Активная вкладка получила мягкую cyan/violet/pink подсветку, тонкий градиентный контур и деликатный движущийся световой блик.',
    'Неактивные кнопки стали спокойнее и меньше, а hover получил лёгкую подсветку без яркого визуального шума.',
    'Размеры иконок, отступы и бейдж очереди уменьшены под общий премиальный dark-дизайн ENDLUME.',
    'Функциональность кнопок и остальная часть приложения не изменялись.'
  ]},
  {version:'1.0.0-alpha.8.11',date:'15.08.2026',title:'Полная история релизов и финальная нормализация имени',items:[
    'История обновлений теперь показывает все сохранённые alpha-релизы от 8.1 до текущей версии, включая ранее скрытые 8.1 и 8.2.',
    'Каждый релиз раскрывается отдельным блоком: дата, версия и полный список изменений.',
    'Каноническое имя macOS-приложения закреплено как «ENDLUME Studio.app»; старые названия вроде «ENDLUME Studio alpha8.3 backup» автоматически переносятся в /Applications/ENDLUME Studio.app.',
    'Сохранена исправленная диагностика Fast Engine из alpha.8.10: выбранным может быть только реально работающий кодировщик.'
  ]},
  {version:'1.0.0-alpha.8.10',date:'15.08.2026',title:'Fast Engine benchmark без ложных результатов',items:[
    'Исправлена ошибка, из-за которой Benchmark мог показывать «Выбран: libx264», одновременно отмечая libx264 как недоступный.',
    'Benchmark сначала проверяет список кодировщиков комплектного FFmpeg, затем реально создаёт короткий MP4 каждым доступным движком.',
    'На Mac отдельно тестируются h264_videotoolbox, hevc_videotoolbox и libx264. Победителем может стать только кодировщик, который реально создал корректный тестовый файл.',
    'Если движок не работает, ENDLUME показывает реальную причину ошибки FFmpeg вместо безликой надписи «недоступен».',
    'Для VideoToolbox тест использует реальный MP4-контейнер, yuv420p и разрешение программного fallback, чтобы не получать ложный отказ от null-muxer.',
    'Ноль файлов в «Кэш Effects» явно поясняется как нормальное состояние до первой подготовки эффекта.'
  ]},
  {version:'1.0.0-alpha.8.9',date:'15.08.2026',title:'Одна установка и постоянные уведомления об обновлениях',items:[
    'На macOS введён жёсткий канонический путь: /Applications/ENDLUME Studio.app. Обновление больше не должно создавать рядом вторую копию приложения.',
    'Перед установкой обновления Single App Guard удаляет старые дубликаты с тем же bundle ID. Если ENDLUME запущена из другого места, приложение сначала переносится в /Applications и перезапускается.',
    'После обновления выполняется повторная проверка дубликатов. При следующем запуске ENDLUME также автоматически чистит оставшиеся клоны.',
    'Проверка обновлений работает при запуске, каждые 5 минут и при возврате в окно приложения.',
    '«Напомнить через час» временно скрывает карточку, после чего уведомление снова появляется автоматически.'
  ]},
  {version:'1.0.0-alpha.8.8',date:'15.08.2026',title:'История обновлений и нормальное имя приложения',items:[
    'Добавлена история alpha-релизов прямо в Настройки → Обновления.',
    'ENDLUME приводит имя текущего macOS app-bundle к каноническому «ENDLUME Studio.app», даже если старая установка называлась «alpha8.3 backup» или иначе.',
    'Single App Guard проверяет количество копий, bundle ID и правильное имя текущего приложения.',
    'После нормализации имени ENDLUME перезапускается уже из «ENDLUME Studio.app».'
  ]},
  {version:'1.0.0-alpha.8.7',date:'15.08.2026',title:'Single App Guard и плавный редактор',items:[
    'Single App Guard ищет старые копии с тем же bundle ID и оставляет одну актуальную программу.',
    'Подписанный Tauri Updater обновляет текущий app-bundle in-place и выполняет автоматический перезапуск.',
    'Перетаскивание и масштабирование Effects/Subscribe вынесено из React-state: рамка двигается через requestAnimationFrame, состояние сохраняется после отпускания мыши.',
    'Сохранены VideoToolbox Preview, pre-scaled lossless overlay-cache, ВКЛ/ВЫКЛ/удаление Effects, Subscribe, Ambient и живая SSD-телеметрия.'
  ]},
  {version:'1.0.0-alpha.8.6',date:'14.08.2026',title:'Effects, Live Preview и ускорение overlay',items:[
    'Новая macOS-иконка ENDLUME: чистый цветной знак без старой двойной рамки.',
    'Subscribe, Effects и ambient получили отдельные глобальные ВКЛ/ВЫКЛ — настройки не теряются при временном отключении.',
    'Subscribe можно удалить прямо из редактора; у каждого пресета есть явное включение/выключение.',
    'Live Preview больше не запускает FFmpeg и запись на диск на каждый пиксель движения мыши; реальный preview обновляется после отпускания.',
    'Предпросмотр на Mac переведён на Apple VideoToolbox, 60 FPS и короткий 960×540 proxy.',
    'Кэш chromakey/luma заранее уменьшает overlay-клипы до нужного размера вместо обработки полноразмерного 4K overlay при каждом рендере.',
    'Финальное разрешение и выбранный битрейт сохраняются; аудио кодируется один раз при необходимости обработки, финальный mux выполняется stream-copy.',
    'В Render Center показывается реальный SSD: использовано / свободно / всего, обновление каждую секунду.'
  ]},
  {version:'1.0.0-alpha.8.5',date:'13.08.2026',title:'Уведомление об обновлении',items:[
    'Новое обновление появляется отдельным уведомлением сверху слева и не перекрывает рабочий экран.',
    'Добавлены кнопки «Обновить» и «Обновить позже».',
    'Прогресс скачивания и установки показывается прямо в карточке обновления.',
    'После установки ENDLUME автоматически перезапускается; «Обновить позже» скрывает карточку до следующего запуска.'
  ]},
  {version:'1.0.0-alpha.8.4',date:'13.08.2026',title:'Подписанный встроенный Updater',items:[
    'Встроен подписанный ENDLUME Updater: проверка обновлений при запуске и вручную из Настроек.',
    'Новое обновление показывает версию, дату и список изменений; установка выполняется внутри ENDLUME с прогрессом и автоматическим перезапуском.',
    'Обновления проверяются через постоянный HTTPS-канал ENDLUME; Terminal и повторная установка приложения после этой версии больше не нужны.',
    'Каждый update-пакет проверяется криптографической подписью перед установкой.'
  ]},
  {version:'1.0.0-alpha.8.3',date:'13.08.2026',title:'Smart Size и быстрый статичный master',items:[
    'Smart Size переделан на короткий 8–12-секундный master: качественный первый keyframe + низкий bitrate повторяющихся статичных кадров.',
    'Первые 0–5 секунд защищены отдельным high-quality I-frame.',
    'Для статичной картинки используется короткий libx264 Smart Size master, затем stream-copy.',
    'Нижняя панель проекта закреплена у нижней границы окна.'
  ]},
  {version:'1.0.0-alpha.8.2',date:'13.08.2026',title:'Render Center, таймеры и качество Static Master',items:[
    'Таймеры «Прошло» и «Осталось» идут непрерывно между событиями FFmpeg, без остановок и скачков.',
    'Кнопки Render Center приведены к DARK-дизайну ENDLUME / LoopForge и больше не отображаются белыми системными кнопками.',
    '«Открыть видео» и «Открыть папку вывода» переведены на нативные команды macOS/Finder.',
    'В ресурсах отображались память приложения, всего, свободно и занято системой.',
    'Для статичной картинки добавлен Static Master Engine: короткий quality-based H.264 master, затем stream-copy.',
    'Убрана ABR-деградация первых секунд; AudioToolbox AAC поднят до 320 кбит/с / 48 kHz stereo.',
    'Smart Size ориентирован примерно на 1.0–1.2 ГБ для двух часов статичного 4K-контента.',
    'Версия и история изменений получили даты обновления.'
  ]},
  {version:'1.0.0-alpha.8.1',date:'13.08.2026',title:'Standalone macOS и первый Fast Engine',items:[
    'Добавлена standalone-сборка .app: после установки Terminal больше не нужен.',
    'Добавлены Smart Size для проектов с изображением и Fast Engine для Apple Silicon M1+.',
    'CPU/RAM перестали очищаться между событиями прогресса.',
    'UI/UX зафиксирован максимально близко к LoopForge; старый PowerShell/WPF-подход заменён на Tauri 2 + Rust.'
  ]}
];

export function ReleaseHistory(){
  return <section style={{marginTop:28,borderTop:'1px solid #262c3d',paddingTop:20}}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,marginBottom:12}}>
      <div><h4 style={{margin:'0 0 5px',fontSize:13,letterSpacing:'.25px'}}>ИСТОРИЯ ОБНОВЛЕНИЙ</h4><p className="settingsNote" style={{margin:0}}>Все сохранённые релизы ENDLUME Studio. Нажмите на версию, чтобы посмотреть полный список изменений.</p></div>
      <span style={{fontSize:10,color:'#8f98b4',border:'1px solid #30374d',borderRadius:999,padding:'6px 9px',whiteSpace:'nowrap'}}>{releases.length} версий</span>
    </div>
    <div style={{display:'grid',gap:8}}>{releases.map((release,index)=><details key={release.version} open={index===0} style={{border:'1px solid #292f42',borderRadius:10,background:'#0d111c',overflow:'hidden'}}>
      <summary style={{cursor:'pointer',listStyle:'none',display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,padding:'12px 14px',userSelect:'none'}}>
        <span style={{display:'flex',alignItems:'center',gap:9,minWidth:0}}><strong style={{fontSize:11,color:'#eef1fa'}}>{release.version}</strong>{release.current&&<em style={{fontStyle:'normal',fontSize:8,color:'#43d5a0',border:'1px solid #285c4b',borderRadius:999,padding:'3px 6px'}}>ТЕКУЩАЯ</em>}<span style={{fontSize:9,color:'#77819e',whiteSpace:'nowrap'}}>{release.date}</span></span>
        <span style={{fontSize:10,color:'#8b85ff'}}>ПОКАЗАТЬ ▾</span>
      </summary>
      <div style={{padding:'0 14px 13px',borderTop:'1px solid #202638'}}><b style={{display:'block',fontSize:11,marginTop:12,color:'#dfe4f2'}}>{release.title}</b><ul style={{margin:'9px 0 0',paddingLeft:19,color:'#818ba8',fontSize:10,lineHeight:1.55}}>{release.items.map(item=><li key={item} style={{margin:'5px 0'}}>{item}</li>)}</ul></div>
    </details>)}</div>
  </section>
}
