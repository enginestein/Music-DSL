# Editor support for the Music DSL

## VS Code

Open this folder as an extension during development:

```
code editors/vscode
```

Then press `F5` to launch an Extension Development Host, or package it:

```
npm install -g @vscode/vsce
cd editors/vscode && vsce package
code --install-extension music-dsl-3.0.0.vsix
```

Files ending in `.music` get full syntax highlighting.

## Vim / Neovim

Using vim-plug:

```vim
Plug '~/path/to/music/editors/vim', {'rtp': 'vim/'}
```

Or copy the files manually:

```
cp editors/vim/syntax/music.vim  ~/.vim/syntax/
cp editors/vim/ftdetect/music.vim ~/.vim/ftdetect/
```

Neovim (`~/.config/nvim/`):

```
cp -r editors/vim/{syntax,ftdetect} ~/.config/nvim/
```
