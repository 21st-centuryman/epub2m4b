
<div align="center">

## epub2m4b

### A Ebook to audiobook converter using chatterboxtts

![](https://img.shields.io/badge/docker-2496ED.svg?style=for-the-badge&logoColor=white&logo=docker)
![](https://img.shields.io/badge/htmx-3366CC.svg?style=for-the-badge&logoColor=white&logo=htmx)
![](https://img.shields.io/badge/pytoch-EE4C2C.svg?style=for-the-badge&logoColor=white&logo=pytorch)
</div>

## ⇁  Welcome

This is a small hackathon project to convert epub files to m4b (audiobook) files using [chatterbox](https://github.com/resemble-ai/chatterbox). It requires a hefty GPU for some longer paragraphs (lots of ram), if this is an issue I recommend using the cpu as the back end.

We have also a `Dockerfile` and a `example-compose.yml` for those that want to use docker. The website generated is quite simply and easy to understand. There might be updates to this project but I wouldn't hold my breath.

Note, you need to provide your own audio prompt, as long as you name it `prompt.wav` and add it to the root of this directory it should work just fine.
