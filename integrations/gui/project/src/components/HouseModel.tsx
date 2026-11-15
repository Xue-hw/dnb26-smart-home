interface HouseModelProps {
  doorOpen: boolean | undefined;
  windowOpen: boolean | undefined;
  fanOn: boolean | undefined;
  lightOn: boolean | undefined;
  brightness: number;
  temperature?: number;
  humidity?: number;
}

export function HouseModel({ doorOpen, windowOpen, fanOn, lightOn, brightness, temperature, humidity }: HouseModelProps) {
  const illuminated = lightOn === undefined ? undefined : lightOn && brightness > 0;
  const temperatureText = typeof temperature === 'number' ? `${temperature.toFixed(1)}°` : '--°';
  const humidityText = typeof humidity === 'number' ? `${humidity.toFixed(0)}%` : '--%';
  const indicators = [
    { name: '门', active: doorOpen },
    { name: '窗', active: windowOpen },
    { name: '扇', active: fanOn },
    { name: '灯', active: illuminated },
  ];

  return <svg className="house-model" viewBox="0 0 720 460" role="img" aria-label={`智能家居二维设备示意图：温度${temperatureText}，湿度${humidityText}，门${doorOpen === undefined ? '未知' : doorOpen ? '开启' : '关闭'}，窗${windowOpen === undefined ? '未知' : windowOpen ? '开启' : '关闭'}，风扇${fanOn === undefined ? '未知' : fanOn ? '运行' : '停止'}，灯${illuminated === undefined ? '未知' : illuminated ? '开启' : '关闭'}`}>
    <defs>
      <pattern id="houseGrid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#31506a" strokeWidth="1" opacity=".18" /></pattern>
      <linearGradient id="flatScreen" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#173b70" /><stop offset=".55" stopColor="#176ba7" /><stop offset="1" stopColor="#22b9dd" /></linearGradient>
      <radialGradient id="flatLampGlow"><stop stopColor="#fff4a3" stopOpacity=".9" /><stop offset=".35" stopColor="#f3c84c" stopOpacity=".32" /><stop offset="1" stopColor="#f3c84c" stopOpacity="0" /></radialGradient>
      <linearGradient id="flatWood" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#56452f" /><stop offset="1" stopColor="#3b3127" /></linearGradient>
    </defs>

    <rect width="720" height="460" rx="14" fill="#0b1a29" />
    <rect width="720" height="460" rx="14" fill="url(#houseGrid)" />
    <path d="M0 401H720V460H0Z" fill="#0e2234" />
    <path d="M54 401H666" stroke="#31536d" strokeWidth="2" />
    <path d="M92 414H628" stroke="#1b374c" strokeWidth="1" strokeDasharray="5 8" />

    {/* 原 GUI 的正面二维房屋主体 */}
    <rect x="120" y="170" width="480" height="230" rx="5" fill="url(#flatWood)" stroke="#8b7351" strokeWidth="3" />
    {Array.from({ length: 9 }, (_, index) => <path key={index} d={`M123 ${194 + index * 23}H597`} stroke="#a3895f" strokeWidth="1" opacity=".14" />)}
    <path d="M103 170 360 61 617 170Z" fill="#40352f" stroke="#79634d" strokeWidth="3" strokeLinejoin="round" />
    <path d="M146 151H574M195 132H525M246 112H474M298 91H422" stroke="#8f7458" strokeWidth="1" opacity=".2" />
    <path d="M119 170H601" stroke="#b49a70" strokeWidth="5" opacity=".45" />

    {/* 屋顶风扇 */}
    <path d="M340 90 360 69 380 90" fill="#263847" stroke="#607487" strokeWidth="2" />
    <g className={fanOn ? 'fan-blades spinning' : 'fan-blades'}>
      <ellipse cx="360" cy="48" rx="8" ry="23" fill="#91a8c4" />
      <ellipse cx="360" cy="96" rx="8" ry="23" fill="#91a8c4" />
      <ellipse cx="336" cy="72" rx="23" ry="8" fill="#7e96b2" />
      <ellipse cx="384" cy="72" rx="23" ry="8" fill="#7e96b2" />
    </g>
    <circle cx="360" cy="72" r="10" fill="#a8b6c3" stroke="#52697c" strokeWidth="3" />
    <circle cx="360" cy="72" r="3" fill="#23394a" />

    {/* 灯光开启时，窗户与门缝透出暖光 */}
    {illuminated && <g opacity={.25 + brightness / 180} className="light-transition">
      <ellipse cx="426" cy="283" rx="155" ry="100" fill="url(#flatLampGlow)" opacity=".22" />
      <rect x="465" y="205" width="105" height="90" rx="3" fill="#f4c94f" opacity=".2" />
      <rect x="340" y="275" width="85" height="125" rx="2" fill="#f4c94f" opacity=".12" />
    </g>}

    {/* 左侧蓝色 LCD */}
    <g>
      <rect x="150" y="199" width="170" height="83" rx="7" fill="#111e29" stroke="#516477" strokeWidth="3" />
      <rect x="160" y="209" width="150" height="56" rx="3" fill="url(#flatScreen)" />
      <path d="M170 222H203M170 253H210" stroke="#b8edff" strokeWidth="2" opacity=".35" />
      <text x="235" y="248" textAnchor="middle" fill="#dcf8ff" fontSize="27" fontWeight="700" fontFamily="ui-monospace, monospace">{temperatureText}</text>
      <text x="235" y="278" textAnchor="middle" fill="#6f899c" fontSize="8" letterSpacing="2">ENVIRONMENT LCD</text>
      <circle cx="143" cy="206" r="4" fill="#90a1ae" /><circle cx="327" cy="274" r="4" fill="#90a1ae" />
    </g>

    {/* 温湿度传感器模块 */}
    <g>
      <rect x="150" y="302" width="75" height="72" rx="6" fill="#172b3a" stroke="#4c6374" strokeWidth="2" />
      <path d="M176 317v21a9 9 0 1 0 10 0v-21a5 5 0 0 0-10 0Z" fill="none" stroke="#66c6ec" strokeWidth="3" />
      <circle cx="181" cy="347" r="5" fill="#66c6ec" />
      <text x="188" y="366" textAnchor="middle" fill="#9eddf2" fontSize="10" fontFamily="ui-monospace, monospace">{temperatureText}</text>
      <rect x="238" y="302" width="75" height="72" rx="6" fill="#172b3a" stroke="#4c6374" strokeWidth="2" />
      <path d="M275 316q-15 20-15 28a15 15 0 0 0 30 0q0-8-15-28Z" fill="none" stroke="#65a9ed" strokeWidth="3" />
      <text x="276" y="366" textAnchor="middle" fill="#a8c9f3" fontSize="10" fontFamily="ui-monospace, monospace">{humidityText}</text>
    </g>

    {/* 中央门，开门时以二维方式收拢门板 */}
    <g>
      <rect x="338" y="273" width="89" height="127" rx="3" fill="#172028" stroke="#8c7351" strokeWidth="3" />
      <rect x="345" y="280" width="75" height="120" fill={illuminated ? '#6f5b2d' : '#101a20'} />
      <g opacity={doorOpen === undefined ? .2 : 1} className={doorOpen ? 'model-door open' : 'model-door'}>
        <rect x="345" y="280" width="75" height="120" rx="2" fill="#6a5135" stroke="#a3855d" strokeWidth="2" />
        <rect x="355" y="291" width="55" height="40" rx="2" fill="#51402e" stroke="#806a4c" />
        <rect x="355" y="342" width="55" height="43" rx="2" fill="#51402e" stroke="#806a4c" />
        <circle cx="405" cy="338" r="4" fill="#d4bb83" />
      </g>
      <text x="383" y="417" textAnchor="middle" fill={doorOpen ? '#75d9ee' : '#758b9c'} fontSize="10">{doorOpen === undefined ? '门状态未知' : doorOpen ? '门已开启' : '门已关闭'}</text>
    </g>

    {/* 右侧四格窗，开启时左窗扇滑动 */}
    <g>
      <rect x="462" y="202" width="111" height="96" rx="4" fill="#142d40" stroke="#6e7e88" strokeWidth="3" />
      <rect x="469" y="209" width="97" height="82" fill={illuminated ? '#746837' : '#1b3e55'} />
      <g opacity={windowOpen === undefined ? .2 : 1} className={windowOpen ? 'model-window open' : 'model-window'}>
        <rect x="469" y="209" width="47" height="82" fill={illuminated ? '#a18b43' : '#28536b'} stroke="#93a9b4" strokeWidth="2" />
        <path d="M492 209V291M469 250H516" stroke="#a4b5bc" strokeWidth="2" />
      </g>
      <path d="M540 209V291M517 250H566" stroke="#a4b5bc" strokeWidth="2" />
      <rect x="517" y="209" width="49" height="82" fill="none" stroke="#93a9b4" strokeWidth="2" />
      <text x="518" y="315" textAnchor="middle" fill={windowOpen ? '#75d9ee' : '#758b9c'} fontSize="10">{windowOpen === undefined ? '窗状态未知' : windowOpen ? '窗已开启' : '窗已关闭'}</text>
    </g>

    {/* 右下灯光模块 */}
    <g>
      <rect x="463" y="330" width="109" height="58" rx="6" fill="#172b3a" stroke="#4c6374" strokeWidth="2" />
      {illuminated && <circle cx="490" cy="359" r={27 + brightness * .12} fill="url(#flatLampGlow)" className="light-transition" />}
      <circle cx="490" cy="359" r="12" fill={illuminated ? '#f7dc62' : '#4f5d59'} stroke={illuminated ? '#fff1a4' : '#718079'} strokeWidth="2" />
      <path d="M485 373h10M487 378h6" stroke="#9a9b79" strokeWidth="2" strokeLinecap="round" />
      <text x="535" y="355" textAnchor="middle" fill={illuminated ? '#f5dd7e' : '#728796'} fontSize="10">LIGHT</text>
      <text x="535" y="372" textAnchor="middle" fill="#b5c7d4" fontSize="12" fontFamily="ui-monospace, monospace">{lightOn === undefined ? '—' : brightness}%</text>
    </g>

    {/* 原 GUI 右侧状态指示栏 */}
    <g>
      <rect x="623" y="194" width="67" height="206" rx="9" fill="#0d2233" stroke="#29485f" strokeWidth="2" />
      <text x="656" y="214" textAnchor="middle" fill="#5f7e95" fontSize="8" letterSpacing="1">STATUS</text>
      {indicators.map((item, index) => <g key={item.name}>
        <circle cx="640" cy={239 + index * 43} r="6" fill={item.active ? item.name === '灯' ? '#f5cf55' : '#43d0a5' : '#526474'} className={item.active ? 'status-led active' : 'status-led'} />
        <text x="656" y={243 + index * 43} fill="#9db3c3" fontSize="10">{item.name}</text>
        <text x="656" y={258 + index * 43} textAnchor="middle" fill={item.active ? '#8bdccc' : '#526b7e'} fontSize="7">{item.active === undefined ? '?' : item.active ? 'ON' : 'OFF'}</text>
      </g>)}
    </g>

    <g fontFamily="Segoe UI, sans-serif" fontSize="9" letterSpacing="1.5"><text x="360" y="438" textAnchor="middle" fill="#547188">DnB26 / 2D DEVICE SCHEMATIC</text><text x="600" y="438" textAnchor="end" fill="#416078">LIVE STATE</text></g>
  </svg>;
}
