
<div align="center">

## epub2m4b

### A local Ebook to Audiobook converter using chatterbox-tts

![](https://img.shields.io/badge/docker-2496ED.svg?style=for-the-badge&logoColor=white&logo=docker)
![](https://img.shields.io/badge/htmx-3366CC.svg?style=for-the-badge&logoColor=white&logo=htmx)
![](https://img.shields.io/badge/ffmpeg-007808.svg?style=for-the-badge&logoColor=white&logo=ffmpeg)
</div>

## ⇁  Welcome

This is a small hackathon project to convert epub files to m4b (audiobook) files using [chatterbox](https://github.com/resemble-ai/chatterbox). It requires a hefty GPU for some longer paragraphs (lots of ram), if this is an issue I recommend using the cpu as the back end.

the entire project is a website written in [htmx](https://htmx.org). To run and host it simply run:
```bash
python3 -m pip install -r requirements.txt
pyhton3 app.py
```

We have also a `Dockerfile` and a `example-compose.yml` for those that want to use docker. The website generated is quite simply and easy to understand. There might be updates to this project but I wouldn't hold my breath.

Note, you need to provide your own audio prompt, as long as you name it `prompt.wav` and add it to the root of this directory it should work just fine.
