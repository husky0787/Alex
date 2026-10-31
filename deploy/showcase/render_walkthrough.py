"""Render a silent evidence walkthrough; this is explicitly not a UI recording.

uv run --no-project --with pillow --with imageio-ffmpeg deploy/showcase/render_walkthrough.py
"""
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'docs/showcase'
SLIDES = [
    ('01 / PROJECT', 'Alex: evidence you can inspect',
     'Course foundation. Personal engineering extension.',
     ['Verified daily data and recoverable ETL', 'Fixed prices for reproducible AI analysis',
      'Kubernetes operations and controlled delivery'], 'Recorded acceptance: 31 October 2026'),
    ('02 / TRACE A PRICE', 'From source to dated history', 'Massive -> raw archive -> validation -> database -> UI',
     ['AAPL: $344.63 close | trading date 2026-10-30', '64 / 64 expected sessions available',
      '20 stocks and ETFs | 1,280 verified daily bars'], 'Actual provider data; end-of-day bars, not live quotes'),
    ('03 / FOLLOW A JOB', 'One real authenticated analysis', 'Clerk -> API -> frozen prices -> SQS -> Planner',
     ['Reporter + Charter + Retirement persisted results', 'Observed completion: 37.195 seconds',
      'Sample holdings: 1 AAPL, 2 MSFT, $1,000 cash'], 'Fictional portfolio; one observation, not a performance benchmark'),
    ('04 / VERIFY THE BASIS', 'What did the report actually use?', 'Read back persisted data; do not trust transport status alone.',
     ['Report and retirement hashes match the price snapshot', 'Chart holdings match frozen quantities and prices',
      'Research identity, source URL and capture time preserved'], 'Tagger: separate preflight. Researcher capture: earlier Task6 run.'),
    ('05 / FIND KUBERNETES', 'API Deployment + ETL CronJob', 'Agents remain Lambda workloads.',
     ['Task9: real EKS permissions, alerts, recovery and rollback', 'Task10: image digests, OIDC / ECR and CI rollback',
      'Task11: local API + real Clerk and AWS analysis'], 'Separate acceptance environments; EKS delivery remains an operator step'),
    ('06 / REPRODUCE', 'Source, runbooks and honest limits', 'github.com/husky0787/Alex | docs/showcase',
     ['Inspect original-course vs personal-contribution boundaries', 'Review resource ownership; archive before cleanup',
      'Rebuild using your own credentials and approved budget'], 'Final billing is pending. This is not an always-on demo.'),
]


def font(size, bold=False):
    candidates = [Path('C:/Windows/Fonts') / ('segoeuib.ttf' if bold else 'segoeui.ttf'),
                  Path('/usr/share/fonts/truetype/dejavu') / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    raise RuntimeError('Install Segoe UI or DejaVu Sans before rendering')


def frame(slide, progress):
    label, title, subtitle, bullets, footnote = slide
    result = Image.new('RGB', (1280, 720), '#0d1726')
    draw = ImageDraw.Draw(result)
    draw.rounded_rectangle((48, 40, 1232, 680), radius=24, fill='#152438', outline='#2a405c', width=2)
    draw.text((84, 68), label, font=font(22, True), fill='#61d7c0')
    draw.text((84, 126), title, font=font(42, True), fill='#f4f7fc')
    draw.text((84, 195), subtitle, font=font(25), fill='#b5c8df')
    y = 294
    for text in bullets:
        draw.ellipse((86, y + 12, 96, y + 22), fill='#61d7c0')
        lines = textwrap.wrap(text, 69)
        for line in lines:
            draw.text((120, y), line, font=font(27), fill='#eef4fc')
            y += 40
        y += 20
    draw.text((84, 566), footnote, font=font(20), fill='#a9bdd4')
    draw.text((84, 622), 'EVIDENCE WALKTHROUGH  |  Not a live browser recording', font=font(18, True), fill='#e8bd70')
    draw.rectangle((48, 700, 48 + int(1184 * progress), 706), fill='#61d7c0')
    return result


def render():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(str(OUTPUT / 'walkthrough.mp4'), (1280, 720), fps=10,
                                        codec='libx264', quality=8, macro_block_size=16,
                                        output_params=['-movflags', '+faststart'])
    writer.send(None)
    previews = []
    try:
        for index, slide in enumerate(SLIDES):
            still = frame(slide, (index + 1) / len(SLIDES))
            previews.append(still)
            for tick in range(75):
                picture = frame(slide, (index * 75 + tick + 1) / 450)
                writer.send(picture.tobytes())
    finally:
        writer.close()
    previews[0].save(OUTPUT / 'walkthrough-poster.png')
    contact = Image.new('RGB', (1280, 1080))
    for index, picture in enumerate(previews):
        picture.thumbnail((640, 360))
        contact.paste(picture, ((index % 2) * 640, (index // 2) * 360))
    private = ROOT / '.local/showcase/walkthrough-contact-private.png'
    private.parent.mkdir(parents=True, exist_ok=True)
    contact.save(private)
    print('Rendered45-second silent results walkthrough and private contact sheet.')


if __name__ == '__main__':
    render()
