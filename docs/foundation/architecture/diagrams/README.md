# Архитектурные схемы AgroVision

Схемы сверены с **реализованным Android online MVP**. Mobile draft сейчас в памяти; private files находятся на локальном persistent volume. Web, экспертная annotation, поля/сезоны и persistent offline queue явно отмечены как будущие возможности. Research candidates всегда сопровождаются inconclusive; схемы не утверждают diagnostic readiness.

| Схема | Редактируемый текст | Векторный экспорт | Растровый экспорт |
|---|---|---|---|
| Контекст | [context.mmd](context.mmd) | [context.svg](context.svg) | [context.png](context.png) |
| Компоненты | [components.mmd](components.mmd) | [components.svg](components.svg) | [components.png](components.png) |
| UML Use Case | [use_cases.puml](use_cases.puml) | [use_cases.svg](use_cases.svg) | [use_cases.png](use_cases.png) |

Mermaid-исходники содержат узлы/связи контекста и компонентов. PlantUML-исходник содержит настоящие UML actors, system boundary, use cases, `include` и `extend`; это не flowchart под названием Use Case. SVG остается редактируемым вектором; PNG удобен для вставки в документы.

Экспорты сверстаны по тем же смысловым узлам и связям с помощью [render_diagrams.py](render_diagrams.py), а не выдаются за автоматическую раскладку Mermaid/PlantUML. Скрипт одновременно рисует SVG и PNG из одной геометрии. При изменении содержания согласованно обновить текстовый source и экспортную спецификацию. Скрипт — вспомогательный генератор документации, не исходный код приложения.

Для воспроизведения экспортов требуется Python, Pillow и DejaVu Sans либо Noto Sans по путям в начале скрипта; при другой ОС заменить пути к шрифтам. Запуск из этой папки: `python render_diagrams.py`. Это команда генерации иллюстраций, не команда запуска AgroVision.

Проверка согласованности: контекст — 5 узлов, 7 направленных связей (2 будущие экспертные связи пунктиром); компоненты — 9 компонентных узлов и 10 связей, API/worker/runtime сгруппированы в одном backend application; use-case — 3 актера, 12 нумерованных целей и 2 включаемые проверки, 14 связей участия, 2 `include`, 1 `extend`. SVG-подписи используют переносы строк для читабельности без изменения смысла.

При использовании растровых файлов сохранять пропорции. Для печати/увеличения предпочтителен SVG. В проекте допустим другой renderer исходников, если смысл, направления связей и читаемость сохраняются.
