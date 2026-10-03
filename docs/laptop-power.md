# Laptop Power — настройка энергосбережения (little-raven)

Цель: профиль «Экономия энергии» держит батарею максимально долго, при
этом профили «Сбалансированный» и «Производительность» не ограничены —
максимальная мощность всегда доступна.

[Обзор рабочих станций](workstations.md) · [Обзор репозитория](../README.md).

## Принцип

Все настройки делятся на два класса:

1. **Profile-scoped** — действуют только пока активен конкретный профиль
   (переключение — стандартный виджет KDE, за ним стоит
   `power-profiles-daemon`). TLP и auto-cpufreq сознательно не
   используются: они конфликтуют с ppd и ломают переключатель в KDE.
2. **Idle-power knobs** — глобальные, но влияют только на потребление
   в простое (состояния сна устройств), не на пиковую производительность.

Таким образом ни одна настройка не «отнимает» мощность у профиля
`performance`.

## Что делает роль `laptop_power`

| Мера | Тип | Эффект |
| --- | --- | --- |
| Turbo off в `power-saver` (`ppd-saver-extras.service`, watcher по D-Bus, `intel_pstate/no_turbo=1`) | profile-scoped | меньше пиковый жар и расход в экономном профиле; в остальных профилях turbo возвращается |
| Потолок CPU 60% в `power-saver` (`max_perf_pct`, ~3 ГГц) | profile-scoped | главный рычаг под нагрузкой; осознанная медленность — суть профиля |
| Потолок iGPU 500 МГц в `power-saver` (`gt_max_freq_mhz`, RP0=1300) | profile-scoped | браузер/видео не разгоняют iGPU; при dual-channel (32 ГБ) полосы хватает, чтобы не замечать кап |
| Wi-Fi power save в `power-saver` (тот же watcher + NM-dispatcher на reconnect) | profile-scoped | один из самых заметных пунктов на батарее; в `balanced`/`performance` PS выключен — ноль влияния на джиттер |
| Пол CPU 25% + пол iGPU 400 МГц в `performance` (`min_perf_pct`, `gt_min_freq_mhz`) | profile-scoped | убирает латентность разгона под нагрузкой; цена — чуть больше в простое, и только в этом профиле |
| HDA codec sleep (`power_save=1`, было 0 = никогда не спит) | idle knob | ~0.5–1 Вт в простое |
| PCIe ASPM `powersupersave` (было `default`) | idle knob | сон линий PCIe/NVMe в простое |
| PCI runtime PM для Wi-Fi/Ethernet/NVMe (udev, `power/control=auto`) | idle knob | ~0.3–0.8 Вт в простое; ломает Wake-on-LAN на Ethernet |
| scx_loader + `scx_lavd` (sched-ext, `/etc/scx_loader/config.toml`) | profile-scoped | ppd в CachyOS пропатчен и сам переключает режим планировщика: saver → PowerSave (`--powersave` + core compaction), balanced → Auto (autopilot), performance → Gaming (`--performance`) |
| Пороги заряда 75/80 (`charge_control_*_threshold`) | здоровье батареи | меньше износ при работе от сети; нужен максимум времени от одного заряда — поставь `laptop_power_charge_end_threshold: 100` в `inventory/host_vars/little-raven/power.yml` |

Источники конфигурации: [роль](../roles/laptop_power/tasks/main.yml),
[текущие значения по умолчанию](../roles/laptop_power/defaults/main.yml) и
[настройки little-raven](../inventory/host_vars/little-raven/power.yml).
Playbook — [playbooks/workstation.yml](../playbooks/workstation.yml), тег `power`.
Числа в описании профилей относятся к текущим defaults; host_vars могут их
переопределить. Настройки исторических замеров ниже не обновляются вместе с defaults.

Runtime-состояние применяют разные механизмы:

- tmpfiles — ASPM, audio и пороги заряда: при загрузке и при изменении файла ролью;
- watcher — CPU/GPU/Wi-Fi: при старте/рестарте и смене профиля;
- udev — PCI runtime PM: для новых устройств и через trigger при изменении правила;
- NM-dispatcher — Wi-Fi power save при переподключении.

Повторный прогон с неизменёнными файлами не сбрасывает любой ручной runtime drift.

### Как работает extras-watcher

У ppd нет per-profile хуков, поэтому `/usr/local/bin/ppd-saver-extras`
(системный сервис `ppd-saver-extras.service`) следит за
`ActiveProfile` на системной шине (`gdbus monitor`) и выставляет
полное состояние для каждого профиля:

- `power-saver` → `no_turbo=1`, `max_perf_pct=60`, `gt_max=500`, Wi-Fi PS on
- `performance` → полы `min_perf_pct=25`, `gt_min=400`, остальное дефолт
- `balanced` (и всё остальное) → **явно дефолты ядра**: `no_turbo=0`,
  `min_perf_pct=0`, `max_perf_pct=100`, GPU по заводским RPn/RP0
  (читаются из железа, не хардкод), Wi-Fi PS off

При штатной конфигурации переход в `balanced` явно восстанавливает CPU/GPU
и включённые profile-scoped настройки turbo/Wi-Fi. Это не откат глобальных
ASPM/audio/PCI/charge-настроек. GPU-границы watcher читает из аппаратных
`gt_RP0/RPn_freq_mhz`, а не из сохранённого состояния до установки роли;
эта логика рассчитана на интерфейс i915.

Так как iwlwifi сбрасывает power_save при каждом
переподключении, рядом стоит NM-dispatcher
(`/etc/NetworkManager/dispatcher.d/50-ppd-wifi-powersave`), который
выставляет состояние по текущему профилю при каждом `up`.
Если watcher упал/не запущен — система просто остаётся в текущем
состоянии (fail-open).

## Применение

```bash
# только power-слой:
ansible-playbook playbooks/workstation.yml -c local --limit little-raven --tags power --ask-become-pass
# или полный прогон по tailnet:
ansible-playbook playbooks/workstation.yml --limit little-raven
```

При старте или рестарте extras-watcher сразу применяет текущий профиль.
Уже работающий watcher не перезапускается при неизменённом шаблоне; для
повторного применения переключите профиль или перезапустите
`ppd-saver-extras.service`. tmpfiles и udev применяются при изменении их файлов.

## Замеры

Методика: отключить зарядку, яркость не менять между замерами, закрыть
тяжёлые приложения, дать рабочему столу ~1 минуту устаканиться, затем:

```bash
scripts/power-idle-bench.sh          # 15 сэмплов × 2 с
scripts/power-idle-bench.sh 30 2     # длиннее — точнее
scripts/power-load-bench.sh 60       # фиксированная работа: x264, сравнение Wh/задачу
scripts/power-mixed-bench.sh 600     # окно замера 600 с: всплески + простой
```

Скрипт печатает средний/min/max разряд (Вт) и снапшот ключевых
параметров (профиль, EPP, turbo, ASPM, audio, Wi-Fi PS) — удобно
вставлять в таблицу ниже.

Методики: [idle](../scripts/power-idle-bench.sh),
[fixed-work](../scripts/power-load-bench.sh) и
[mixed](../scripts/power-mixed-bench.sh). Энергия в нагрузочных скриптах —
оценка по среднему sampled power × времени, не отдельное измерение энергии.

### Результаты (little-raven, i7-1355U, KDE idle, яркость 10667/19393)

Исторические наблюдения, не гарантия текущего расхода. Дата, commit/config
snapshot, версии kernel/ppd и исходные логи этих прогонов в репозитории
не сохранены. Для новых замеров сохраняйте их вместе с полным stdout,
яркостью, профилем, длительностью и результатами повторных прогонов.

| Замер          | Профиль     | avg, Вт  | min, Вт | max, Вт | Что включено                                        |
| -------------- | ----------- | -------- | ------- | ------- | --------------------------------------------------- |
| **До**         | balanced    | 9.37     | —       | —       | сток CachyOS (15×2 с)                               |
| Итерация 1     | balanced    | 9.20     | 8.41    | 10.13   | ASPM, audio, Wi-Fi PS, пороги заряда (30×2 с)       |
| Итерация 1     | power-saver | 8.12     | 7.63    | 8.69    | + turbo off в saver                                 |
| **Итерация 2** | balanced    | **5.51** | 5.39    | 5.63    | + PCI runtime PM (Wi-Fi/Eth/NVMe спят)              |
| **Итерация 2** | power-saver | 6.51     | 5.78    | 7.13    | + потолки CPU 60% / GPU 500 МГц                     |
| **Итерация 2** | performance | 6.13     | 5.51    | 6.30    | + полы CPU 25% / GPU 400 МГц (idle-цена по дизайну) |

Итог к стоку: **balanced −41%** (9.37 → 5.51 Вт) — это почти +70% к
времени в простое. Замеры одного профиля сняты подряд с одинаковой
яркостью; между прогонами был ~1 мин паузы на settle.

Два наблюдения:

1. **Смысл saver зависит от режима работы.** Фиксированная работа
   (60 с x264): saver ≈0.124 Wh против 0.062 у balanced — race-to-idle
   выигрывает, потолки вредны. Рваная нагрузка в фиксированное время
   (10 мин, всплеск+пауза): saver 6.91 Вт против 7.84 у balanced (−12%),
   performance провалился до 12.17 Вт (полы мешают спать в паузах).
   Правило: «сделать задачу» → balanced/performance; «сидеть в кафе
   N часов» → saver. Методики — в linked benchmark-скриптах выше;
   подробный исходный отчёт этих прогонов в репозитории отсутствует.
2. **`cpu min` показывает 9, хотя watcher пишет 0 в saver/balanced** —
   ppd переassert'ивает свой `min_perf_pct=9` после нашего обработчика.
   Безвредно: это пол (≈ минимальная частота), на скорость не влияет.

Замера «до» в профиле `power-saver` нет — базовый замер был снят до
установки watcher'а в `balanced`.

## Откат

`laptop_power_enabled: false` в host_vars только пропускает роль; уже
установленные файлы и сервисы остаются. Сначала отключите роль в
[host_vars](../inventory/host_vars/little-raven/power.yml), чтобы следующий deploy
не установил конфигурацию снова.

Ниже — удаление установленной конфигурации, **не полный откат live-состояния**.
Если watcher работает, сначала переключите профиль в `balanced` и проверьте
CPU/GPU-границы, пока он ещё запущен. Для полного отката нужны записанные до
установки значения: остановка сервиса и удаление файлов их не восстанавливают.

```bash
# удалить конфигурацию little-raven; WIFI_IFACE должен совпадать с host/defaults:
WIFI_IFACE=wlan0
sudo systemctl disable --now ppd-saver-extras.service scx_loader.service
sudo rm /etc/systemd/system/ppd-saver-extras.service /usr/local/bin/ppd-saver-extras \
        /etc/scx_loader/config.toml \
        /etc/NetworkManager/dispatcher.d/50-ppd-wifi-powersave \
        /etc/udev/rules.d/99-pci-runtime-pm.rules \
        /etc/tmpfiles.d/laptop-power.conf /etc/modprobe.d/snd-hda-powersave.conf
sudo systemctl daemon-reload
sudo udevadm control --reload
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo iw dev "$WIFI_IFACE" set power_save off
```

После удаления проверьте CPU min/max, GPU min/max, ASPM, audio power-save,
PCI `power/control` и пороги заряда. Верните сохранённые baseline-значения
либо перезагрузитесь для сброса непостоянного состояния и проверьте снова.
Перезагрузка не гарантирует сброс порогов заряда, которые может хранить firmware;
их нужно восстановить отдельно. Не подставляйте универсальные «стоковые»
значения вместо baseline конкретной машины.

## Известные нюансы

- **Wi-Fi PS и латентность**: штатно power save включён только в
  `power-saver`. Для отключения задайте
  `laptop_power_saver_wifi_powersave: false`, примените роль, затем удалите
  ранее установленный `/etc/NetworkManager/dispatcher.d/50-ppd-wifi-powersave`
  и выключите live power save через `iw` для нужного интерфейса.
  Текущая роль при `false` пропускает установку dispatcher, но не удаляет
  старый файл; без удаления он снова включает PS при reconnect в saver.
- **Потолки в `power-saver` — это тишина, а не экономия**: 60% CPU и
  500 МГц GPU дают ровные ~10–13 Вт под нагрузкой без турбо-пиков, но
  энергия НА ЗАДАЧУ выше, чем в balanced (замерено: ×2 на x264).
  Если saver нужен «тихим, но быстрым» —
  подними `laptop_power_saver_cpu_max_perf_pct` до 80–100.
- **Wake-on-LAN** по Ethernet может перестать работать из-за PCI runtime PM.
  Чтобы отказаться от этой настройки, задайте `laptop_power_pci_runtime_pm: false`,
  удалите ранее установленный `/etc/udev/rules.d/99-pci-runtime-pm.rules`,
  перезагрузите правила udev и восстановите нужное live `power/control`.
  Удаление host override вернёт default `true`; значение `false` само по себе
  только пропускает установку правила, не удаляет его и не сбрасывает live state.
- **scx_loader**: в CachyOS power-profiles-daemon ПРОПАТЧЕН и при смене
  профиля сам переключает режим планировщика через D-Bus API loader'а
  (проверено: `scx-loader proxy` есть в бинарнике ppd). Поэтому схема —
  стоковый юнит + `/etc/scx_loader/config.toml` с `default_sched`.
  `--auto` у scx_loader 1.1.3 — это НЕ переключение по профилю, а
  триггер по загрузке CPU (старт lavd при >90%); не используем.
  Проверка: `scxctl get` (показывает планировщик и режим) и
  `cat /sys/kernel/sched_ext/state`. Тонкий тюнинг аргументов режимов —
  секции `[scheds.scx_lavd]` в том же конфиге.
- **Пороги заряда** не влияют на время работы от батареи «здесь и сейчас»,
  только на срок службы ячеек. Перед долгой поездкой временно верни 100.
- **Suspend**: ноутбук умеет только `s2idle` (modern standby), `deep`
  недоступен — поэтому на ночь лучше гибернация либо выключение, это
  вне скоупа роли.
