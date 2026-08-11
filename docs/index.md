# dit

MD計算で扱う大容量ファイルを、Gitとは分離して版管理するCLIツールです。

## インストール

```console
$ pip install git+https://github.com/2lu3/dit.git
```

## 最短の使い方

```console
$ cd /path/to/your-md-project
$ dit init --bucket my-bucket --prefix md-project
$ dit scope add data
$ dit sync
```

[User Guideを読む](guide/getting-started.md){ .md-button .md-button--primary }
[CLI Referenceを見る](reference/index.md){ .md-button }
