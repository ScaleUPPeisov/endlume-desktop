import React from 'react';

type Release={version:string;date:string;current?:boolean;title:string;items:string[]};

const releases:Release[]=[
  {version:'1.0.0-alpha.8.19',date:'24.08.2026',current:true,title:'Chromakey Fidelity + Render Recovery',items:[
    'Chromakey переведён на RGB colorkey: видимые пиксели Effects/Subscribe сохраняют исходный цвет без прежней глобальной saturation/despill коррекции.',
    'В Live Preview добавлена «ПИПЕТКА / КИСТЬ»: можно кликнуть или провести по фону overlay-видео и взять реальный цвет chromakey из исходного кадра.',
    'Старые пресеты с Similarity/Blend около 0.9–1.0 автоматически приводятся к безопасным значениям и получают новый fidelity-cache.',
    'Вторая попытка рендера теперь принудительно переключается с hardware encoder на libx264/libx265 software fallback.',
    'Финальный stream-copy mux получил безопасную генерацию timestamp без повторного кодирования видео или музыки.',
    'FFmpeg-ошибки теперь сохраняют название конкретного этапа, чтобы следующая ошибка была диагностируема, а не скрыта общим сообщением.',
    'Локальный release-gate дополнен отдельным green-screen/colorkey smoke-test и проверкой software encoder retry.'
  ]},
  {version:'1.0.0-alpha.8.18',date:'24.08.2026',title:'Render Recovery: обычные папки, managed overlays и updater timeout',items:[
    'Обычный проект «1 PNG + MP3» теперь входит в обязательный end-to-end release regression и должен собрать валидный MP4 с видео и аудио до публикации обновления.',
    'MP3 с разными sample rate, mono/stereo и Unicode/французскими именами нормализуются перед acrossfade к 48 kHz / stereo / fltp.',
    'Если сохранённые пути PNG/MP3 устарели после обновления или перемещения папки, ENDLUME повторно сканирует саму папку проекта и восстанавливает актуальные пути перед рендером.',
    'Выключенные Effects/Subscribe не обращаются к source-файлам. Включённый overlay с потерянным файлом пропускается с предупреждением и больше не валит основной рендер.',
    'Новые Effects, Subscribe и ambient копируются во внутреннюю managed-библиотеку ENDLUME и не зависят от Downloads/Desktop после импорта.',
    'Проверка обновлений ограничена 12 секундами и больше не должна навсегда оставлять кнопку в состоянии «ПРОВЕРЯЮ…».',
    'Перед созданием подписанного updater release pipeline принудительно применяет render hotfix, 100 Loop Mode smoke-checks, normal-folder regression, Motion/UI checks и Rust/Frontend checks.'
  ]},
  {version:'1.0.0-alpha.8.17',date:'24.08.2026',title:'Hotfix: обычный рендер, Effects/Subscribe и зависание обновлений',items:[
    'Подготовлены исправления stale overlay, mixed-MP3 и updater timeout.',
    'Добавлена managed-библиотека для Effects, Subscribe и ambient.',
    'Добавлено самовосстановление путей проекта перед рендером.'
  ]},
  {version:'1.0.0-alpha.8.16',date:'23.08.2026',title:'Fixed footer и безопасные route-анимации',items:[
    'Нижняя панель «Добавить в очередь» снова закреплена к viewport и не перекрывает параметры после прокрутки.',
    'Корневой route-wrapper больше не использует transform/filter/perspective, которые ломали position: fixed в macOS WKWebView.',
    'Переходы страниц сохранены через лёгкую opacity-анимацию; нативная прокрутка macOS и GPU Live Preview сохранены.',
    'Добавлены 16 обязательных motion/layout проверок release pipeline.'
  ]},
  {version:'1.0.0-alpha.8.15',date:'23.08.2026',title:'Нативная плавная прокрутка macOS',items:[
    'Убраны тяжёлые JS wheel/scroll перехваты и per-frame governor из обычной прокрутки.',
    'Скролл оставлен нативному WKWebView/macOS для максимально стабильного ощущения.',
    'Правый scrollbar скрыт, рабочая область очищена от лишнего визуального шума.'
  ]},
  {version:'1.0.0-alpha.8.14',date:'23.08.2026',title:'Motion Engine: плавная прокрутка и переходы',items:[
    'Добавлен Motion Layer для плавных переходов между разделами и hover/press-анимаций.',
    'Прокрутка и переходы оптимизированы под compositor-friendly свойства.',
    'Добавлены release-проверки motion-архитектуры.'
  ]},
  {version:'1.0.0-alpha.8.13',date:'23.08.2026',title:'GPU Live Preview, LoopForge-полировка и проверка Loop Mode',items:[
    'Effects и Subscribe переведены на GPU Live Preview без FFmpeg на каждом движении.',
    'Положение и размер двигаются вместе с реальным эффектом на частоте дисплея.',
    'Loop Mode проходит 100 FFmpeg smoke-тестов: Image, Crossfade, Ping-pong и Без обработки.',
    'Карточки, значения, пресеты и ползунки приведены к компактному dark-glass стилю.'
  ]},
  {version:'1.0.0-alpha.8.12',date:'15.08.2026',title:'Компактная neon-навигация',items:[
    'Проект, Рендер, Библиотека и Настройки стали компактнее.',
    'Активная вкладка получила cyan/violet/pink подсветку и тонкий градиентный контур.'
  ]},
  {version:'1.0.0-alpha.8.11',date:'15.08.2026',title:'Полная история релизов и нормализация имени',items:[
    'История обновлений вынесена в Настройки → Обновления.',
    'Каноническое имя macOS-приложения закреплено как ENDLUME Studio.app.'
  ]},
  {version:'1.0.0-alpha.8.10',date:'15.08.2026',title:'Fast Engine benchmark без ложных результатов',items:[
    'Benchmark выбирает кодировщик только после реального encode-test.',
    'Проверяются h264_videotoolbox, hevc_videotoolbox и libx264.'
  ]},
  {version:'1.0.0-alpha.8.9',date:'15.08.2026',title:'Одна установка и постоянные уведомления',items:[
    'Канонический путь на Mac: /Applications/ENDLUME Studio.app.',
    'Single App Guard удаляет старые дубликаты с тем же bundle ID.'
  ]},
  {version:'1.0.0-alpha.8.8',date:'15.08.2026',title:'История обновлений и нормальное имя приложения',items:[
    'Добавлена история alpha-релизов.',
    'ENDLUME приводит старые имена app-bundle к ENDLUME Studio.app.'
  ]},
  {version:'1.0.0-alpha.8.7',date:'15.08.2026',title:'Single App Guard и плавный редактор',items:[
    'Single App Guard оставляет одну актуальную ENDLUME.',
    'Drag/resize Effects/Subscribe вынесены из React-state на requestAnimationFrame.'
  ]},
  {version:'1.0.0-alpha.8.6',date:'14.08.2026',title:'Effects, Live Preview и ускорение overlay',items:[
    'Новая macOS-иконка ENDLUME.',
    'Subscribe, Effects и ambient получили ВКЛ/ВЫКЛ.',
    'Preview переведён на Apple VideoToolbox 60 FPS proxy 960×540.',
    'Render Center показывает реальный SSD.'
  ]},
  {version:'1.0.0-alpha.8.5',date:'13.08.2026',title:'Уведомление об обновлении',items:[
    'Добавлены Обновить и Обновить позже.',
    'Прогресс скачивания/установки показывается внутри приложения.'
  ]},
  {version:'1.0.0-alpha.8.4',date:'13.08.2026',title:'Подписанный встроенный Updater',items:[
    'Добавлен подписанный ENDLUME Updater.',
    'Update-пакеты проверяются криптографической подписью.'
  ]},
  {version:'1.0.0-alpha.8.3',date:'13.08.2026',title:'Smart Size и быстрый статичный master',items:[
    'Smart Size использует короткий 8–12-секундный master.',
    'Для статичной картинки применяется короткий master, затем stream-copy.'
  ]},
  {version:'1.0.0-alpha.8.2',date:'13.08.2026',title:'Render Center, таймеры и Static Master',items:[
    'Таймеры Прошло/Осталось идут непрерывно.',
    'Добавлены Static Master Engine и AudioToolbox AAC.'
  ]},
  {version:'1.0.0-alpha.8.1',date:'13.08.2026',title:'Standalone macOS и первый Fast Engine',items:[
    'Добавлена standalone .app-сборка без Terminal после установки.',
    'Добавлены Smart Size и Fast Engine для Apple Silicon M1+.'
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
