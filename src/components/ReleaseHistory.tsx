import React from 'react';

type Release={version:string;date:string;current?:boolean;title:string;items:string[]};

const releases:Release[]=[
  {version:'1.0.0-alpha.8.14',date:'23.08.2026',current:true,title:'Motion Engine: плавная прокрутка и переходы',items:[
    'Добавлен отдельный ENDLUME Motion Layer: переходы между Проектом, Рендером, Библиотекой и Настройками выполняются через compositor-friendly opacity + transform без тяжёлых layout-анимаций.',
    'Прокрутка остаётся нативной для macOS WebView и не перехватывается JavaScript: smooth scroll, overscroll containment, стабильный scrollbar gutter и новый тонкий cyan/violet/pink scrollbar.',
    'Кнопки по всему приложению получили единый короткий press/hover motion, а карточки Настроек, редакторы и раскрытие истории обновлений больше не появляются резким скачком.',
    'Во время активной прокрутки ENDLUME временно приостанавливает декоративные блики и тяжёлые тени, чтобы кадры тратились на сам скролл, а не на косметику.',
    'Добавлен адаптивный FPS governor: requestAnimationFrame оценивает фактическую частоту кадров во время взаимодействия. При устойчивой просадке ниже примерно 48 FPS отключается только тяжёлая декорация; функциональность не меняется.',
    'В release pipeline добавлена отдельная проверка motion-архитектуры: нативный passive scroll, compositor transforms, reduced-motion fallback и отсутствие transition: all.'
  ]},
  {version:'1.0.0-alpha.8.13',date:'23.08.2026',title:'GPU Live Preview, LoopForge-полировка и проверка Loop Mode',items:[
    'Effects и Subscribe переведены на GPU Live Preview: базовый кадр остаётся на экране, а chromakey/luma/screen композятся в WebGL без тяжёлого FFmpeg при каждом движении.',
    'Положение и размер двигаются вместе с реальным эффектом на частоте дисплея. Во время drag/resize React-state и FFmpeg не участвуют; состояние сохраняется после отпускания мыши.',
    'Для первого открытия создаются короткие VideoToolbox proxy в кэше ENDLUME; следующие открытия используют готовый proxy и не дают чёрный экран между изменениями.',
    'Режимы зацикливания проходят отдельный 100-прогонный FFmpeg smoke-test в release pipeline: Image, Crossfade, Ping-pong и Без обработки.',
    'Карточки Loop Mode, числовые значения, пресеты, ползунки и служебные кнопки дополнительно приведены к компактному dark-glass / cyan-violet-pink стилю LoopForge.',
    'Принудительное уменьшение 2-часового файла до 400–500 МБ не добавлялось: такой фиксированный размер нельзя гарантировать одновременно с требованием «строго без потери качества».'
  ]},
  {version:'1.0.0-alpha.8.12',date:'15.08.2026',title:'Компактная neon-навигация',items:[
    'Проект, Рендер, Библиотека и Настройки стали компактнее и аккуратнее.',
    'Активная вкладка получила cyan/violet/pink подсветку, тонкий градиентный контур и движущийся световой блик.',
    'Неактивные кнопки уменьшены; hover получил лёгкую подсветку без лишнего визуального шума.',
    'Логика переходов и остальной функционал не менялись.'
  ]},
  {version:'1.0.0-alpha.8.11',date:'15.08.2026',title:'Полная история релизов и нормализация имени',items:[
    'История обновлений показывает сохранённые alpha-релизы от 8.1 до текущей версии.',
    'Каноническое имя macOS-приложения закреплено как ENDLUME Studio.app.',
    'Старые имена и backup-копии переносятся/очищаются через Single App Guard.',
    'Сохранена исправленная диагностика Fast Engine.'
  ]},
  {version:'1.0.0-alpha.8.10',date:'15.08.2026',title:'Fast Engine benchmark без ложных результатов',items:[
    'Benchmark не может показывать кодировщик выбранным, если реальный encode-test не прошёл.',
    'Проверяются h264_videotoolbox, hevc_videotoolbox и libx264.',
    'Для каждого отказавшего движка показывается реальная причина FFmpeg.',
    'Нулевой Effects cache поясняется как нормальное состояние до первого использования.'
  ]},
  {version:'1.0.0-alpha.8.9',date:'15.08.2026',title:'Одна установка и постоянные уведомления',items:[
    'Канонический путь на Mac: /Applications/ENDLUME Studio.app.',
    'Перед и после обновления Single App Guard удаляет старые дубликаты с тем же bundle ID.',
    'Проверка обновлений запускается при старте, при возврате в окно и каждые 5 минут.',
    'Добавлено отложенное напоминание об обновлении.'
  ]},
  {version:'1.0.0-alpha.8.8',date:'15.08.2026',title:'История обновлений и нормальное имя приложения',items:[
    'Добавлена история alpha-релизов в Настройки → Обновления.',
    'ENDLUME приводит старые имена app-bundle к ENDLUME Studio.app.',
    'Single App Guard проверяет копии, bundle ID и имя текущего приложения.'
  ]},
  {version:'1.0.0-alpha.8.7',date:'15.08.2026',title:'Single App Guard и плавный редактор',items:[
    'Single App Guard оставляет одну актуальную ENDLUME.',
    'Tauri Updater обновляет текущий app-bundle in-place.',
    'Drag/resize Effects/Subscribe вынесены из React-state на requestAnimationFrame.',
    'Сохранены VideoToolbox Preview, overlay-cache, ВКЛ/ВЫКЛ/удаление и SSD-телеметрия.'
  ]},
  {version:'1.0.0-alpha.8.6',date:'14.08.2026',title:'Effects, Live Preview и ускорение overlay',items:[
    'Новая macOS-иконка ENDLUME.',
    'Subscribe, Effects и ambient получили отдельные ВКЛ/ВЫКЛ.',
    'Subscribe можно удалить из редактора.',
    'Preview переведён на Apple VideoToolbox 60 FPS proxy 960×540.',
    'Chromakey/luma cache заранее уменьшает overlay-клипы до рабочего размера.',
    'Render Center показывает реальный SSD: использовано / свободно / всего.'
  ]},
  {version:'1.0.0-alpha.8.5',date:'13.08.2026',title:'Уведомление об обновлении',items:[
    'Карточка нового обновления не перекрывает рабочий экран.',
    'Добавлены Обновить и Обновить позже.',
    'Прогресс скачивания/установки показывается в приложении.',
    'После установки ENDLUME автоматически перезапускается.'
  ]},
  {version:'1.0.0-alpha.8.4',date:'13.08.2026',title:'Подписанный встроенный Updater',items:[
    'Добавлен подписанный ENDLUME Updater.',
    'Обновление устанавливается внутри приложения и показывает версию/дату/изменения.',
    'Пакеты проверяются криптографической подписью.',
    'После этой версии Terminal для обновления не требуется.'
  ]},
  {version:'1.0.0-alpha.8.3',date:'13.08.2026',title:'Smart Size и быстрый статичный master',items:[
    'Smart Size использует короткий 8–12-секундный master.',
    'Первые секунды защищены отдельным high-quality I-frame.',
    'Для статичной картинки используется короткий libx264 master, затем stream-copy.',
    'Нижняя панель проекта закреплена у нижней границы окна.'
  ]},
  {version:'1.0.0-alpha.8.2',date:'13.08.2026',title:'Render Center, таймеры и Static Master',items:[
    'Таймеры Прошло/Осталось идут непрерывно.',
    'Кнопки Render Center приведены к DARK-дизайну ENDLUME/LoopForge.',
    'Открыть видео/папку переведены на нативные команды macOS.',
    'Добавлен Static Master Engine и AudioToolbox AAC 320 кбит/с / 48 kHz stereo.',
    'Smart Size ориентировался примерно на 1.0–1.2 ГБ для двух часов статичного 4K-контента.'
  ]},
  {version:'1.0.0-alpha.8.1',date:'13.08.2026',title:'Standalone macOS и первый Fast Engine',items:[
    'Добавлена standalone .app-сборка: Terminal после установки не нужен.',
    'Добавлены Smart Size и Fast Engine для Apple Silicon M1+.',
    'CPU/RAM перестали очищаться между событиями прогресса.',
    'UI/UX перенесён на Tauri 2 + Rust в стиле LoopForge.'
  ]}
];

export function ReleaseHistory(){
  return <section style={{marginTop:28,borderTop:'1px solid #262c3d',paddingTop:20}}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,marginBottom:12}}>
      <div><h4 style={{margin:'0 0 5px',fontSize:13,letterSpacing:'.25px'}}>ИСТОРИЯ ОБНОВЛЕНИЙ</h4><p className="settingsNote" style={{margin:0}}>Все сохранённые релизы ENDLUME Studio. Нажмите на версию, чтобы посмотреть изменения.</p></div>
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
