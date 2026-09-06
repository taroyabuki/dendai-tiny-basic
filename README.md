# 電大版 Tiny BASIC

安田寿明『マイコンピュータをつかう』（講談社, 1978）の資料5「電大版 Tiny BASIC の概要」をもとに、正規化済みバイナリ、逆アセンブル、実行ハーネス、デモをまとめたものです。出典：[国立国会図書館デジタルコレクション](https://dl.ndl.go.jp/pid/12627293/1/184)

出典の p. (27) を引用します。

> 著作権法にもとづき，著者および講談社の同意を得ずして，次項以降のプログラム内容を営利目的に利用することはできない　１９７８年１月

現在は次を揃えています。

- 正規化済みバイナリ: [`build/dendai-tiny-basic.bin`](/root/work/dendai-tiny-basic/build/dendai-tiny-basic.bin)
- 逆アセンブル結果: [`dendai-tiny-basic.asm`](/root/work/dendai-tiny-basic/dendai-tiny-basic.asm)
- MEK6800D2 quickload: [`build/dendai-tiny-basic.d2`](/root/work/dendai-tiny-basic/build/dendai-tiny-basic.d2)

## このリポジトリでできること

- `dendai-tiny-basic.dump` から補正済みバイナリを生成する
- バイナリから逆アセンブルを再生成する
- ハーネス上で Tiny BASIC を実行し、`LIST` / `RUN` / `INPUT` / `FOR` / `PRINT` などを確認する
- `USR(` からハーネス上の機械語ルーチンを呼び出す
- MAME の `MEK6800D2` 向け quickload イメージを作る

## 必要なもの

- Python 3
- `pytest`
- 生成物を作り直す場合だけ `crasm`
- 生成物を作り直す場合だけ `objcopy`

`build/` 以下の生成物がすでに揃っていれば、まずは Python だけでハーネス実行とテストができます。

## Ubuntu でのセットアップ

Ubuntu では次で最低限の実行環境を入れられます。

```bash
sudo apt update
sudo apt install -y python3 python3-pytest
```

生成物も更新するなら、`crasm` が `universe` にあるので必要なら先に有効化してから次を入れます。

```bash
sudo add-apt-repository universe
sudo apt update
sudo apt install -y binutils crasm
```

## すぐ試す

何も追加指定しなければ、そのまま REPL として使えます。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin
```

`READY` と `#` が出たら、そのまま BASIC の行や direct command を入力できます。`PRINT 2+2` のような immediate statement もそのまま打てます。
REPL では `Ctrl-C` が Tiny BASIC への Break、`Ctrl-D` がホスト側 REPL の終了です。
実行中の `Ctrl-C` は処理を中断して `READY` に戻り、登録済みプログラムを編集・再実行できます。

サンプル BASIC プログラム [`demos/sample.bas`](/root/work/dendai-tiny-basic/demos/sample.bas) をハーネスで流す例です。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/sample.bas
```

`demos/` 以下の BASIC プログラムも同じ形で実行できます。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/<name>.bas
```

たとえば次です。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/mp_array.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/mp_addsub.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/mp_scale.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/mp_div_small.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/pi-010.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/pi-050.bas
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/pi-100.bas
```

既定の `--max-steps` は `120000000` です。`demos/pi-100.bas` も追加指定なしでそのまま実行できます。

直接コマンドを送るなら次です。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin \
  --command '10 PRINT 1' \
  --command 'RUN'
```

出力 transcript を保存したい場合は `--output` を使います。REPL の場合も終了時に transcript を保存します。

```bash
python3 scripts/run_harness.py build/dendai-tiny-basic.bin demos/sample.bas \
  --output build/harness-transcript.txt
```

調査用に `--stop-at-pc`、`--trace-pc`、`--watch-write`、`--dump-memory` も使えます。
命令数上限や未実装命令による停止は終了コード `1`、通常の入力終了・monitor への終了・指定 PC での停止は `0` です。BASIC の `ERROR n` は処理系内で回復する言語エラーであり、ホストの異常停止とは区別します。

## 生成物を更新する

生成物を一式再作成して整合性まで確認する手順です。

```bash
python3 scripts/update_artifacts.py
```

既存生成物の整合性だけを確認する場合は次です。

```bash
python3 scripts/update_artifacts.py --check
```

再生成または確認のあとにテストまで流す場合は次です。

```bash
python3 scripts/update_artifacts.py --test
```

ダンプ中の `$0910-$0911 = 12 34` と `$0916-$0917 = AB CD` は `TO` / `STEP` の位置識別用ダミー値、`$093B-$093F = 05 CE 3D 17 DF` は未参照の埋め草であり、いずれも実行コードではありません。

## 出典掲載の仕様

出典と、現在の dump から再生したキーワード表・構文処理を突き合わせると、この Tiny BASIC は行番号付きプログラム入力と direct mode の両方を持つ整数 BASIC です。以下は言語仕様の整理であり、現行ハーネスでの確認範囲は後述の「確認済み動作」と「制限」に分けています。

**操作**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| 起動 | `READY` | 起動メッセージとして印字表示される |
| prompt | `#` | コマンド入力待ちを表す |
| prompt | `?` | `INPUT` のデータ入力要求を表す |
| 入力形式 | `行番号 文` | プログラム行として登録する |
| 入力形式 | `文` | direct mode で即時実行する |
| 入力形式 | 英字 | 大文字小文字どちらでもよいが、内部では大文字として扱う |
| 入力形式 | 空白 | 文字列中を除き無意味で、内部編集時に吸収される |
| 行番号 | `1` から `32767` | 正整数の範囲をとる |

**コマンドと文**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| コマンド | `NEW` | メモリ内の BASIC プログラムを消去する |
| コマンド | `LIST` | プログラム全体を印字表示する |
| コマンド | `LIST n` | 指定行番号だけを印字表示する |
| コマンド | `LIST n1,n2` | 行番号 `n1` から `n2` までを印字表示する |
| コマンド | `LOAD` | カセット・テープ収録の BASIC プログラムを入力する |
| コマンド | `RUN` | BASIC プログラムを実行する |
| コマンド | `EXIT` | BASIC 処理から monitor へ移行する |
| コマンド | `AUTO n` | 10 の倍数である `n` を初期値として自動行番号入力を開始し、その後は 10 刻みで進める |
| コマンド | `RETURN` | `STOP` で中断している BASIC プログラムの処理を再開する |
| コマンド | `RET` | `RETURN` の省略形 |
| コマンド | `Ctrl-C` | Break を発生させ、処理中の BASIC を中断して direct mode へ戻る |
| 文 | `LET v=e` | 変数へ代入する |
| 文 | `LET @(e)=e` | 配列変数へ代入する |
| 文 | `IF 関係式 文` | 条件が真なら次の文を実行する |
| 文 | `IF 関係式 THEN n` | 条件が真なら指定行へ分岐する |
| 文 | `GOTO n` | 指定行へ分岐する |
| 文 | `GOSUB n` | サブルーチンへ分岐する |
| 文 | `RETURN` | サブルーチンから復帰する |
| 文 | `RET` | `RETURN` の省略形 |
| 文 | `FOR v=m1 TO m2 STEP k` | 変数 `v` を `m1` から `m2` まで `k` 刻みで増やしながらループする。仕様上は `m1 >= 0` かつ `m1 < m2` |
| 文 | `FOR v=m1 TO m2` | `STEP 1` を省略した `FOR` |
| 文 | `NEXT v` | `FOR` ループを進める |
| 文 | `NEXT` | 対応する `FOR` の変数名を省略した `NEXT` |
| 文 | `REM` | 行末までコメントとして扱う |
| 文 | `STOP` | プログラム実行を中断する |
| 文 | `STOP '...'` | 実行を中断し、続くリテラル定数を印字する |
| 文 | `INPUT v1 s v2 s ... s vn` | 変数列を読み込み、必要なら `?` prompt を出す。`s` はセパレータ |
| 文 | `INPUT literal s v1 s ... s vn` | リテラル定数を先に印字してから入力を要求する |
| 文 | `PRINT e` | 式の値を印字する |
| 文 | `PRINT e s e ... s e` | セパレータを交えた複数項目を印字する |
| 文 | `PRINT$` | BASIC プログラム記憶・ユーザー領域サイズを印字する |
| 文 | `END` | プログラム終端 |

**セパレータと編集キー**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| セパレータ | `CR` | コマンドや1個のデータ入力の終端 |
| セパレータ | `,` | `PRINT` の印字を 1 組 8 字ごとにそろえ、`INPUT` では複数入力を区切る |
| セパレータ | `;` | `PRINT` / `INPUT` で文字位置を 1 文字だけ進める |
| セパレータ | `:` | 1 行に複数文を書けるステートメント・セパレータ |
| 編集キー | `Ctrl-O` | 入力中の 1 文字を抹消する |
| 編集キー | `Ctrl-X` | 入力中の 1 行全体を抹消する |

**式と値**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| 算術演算子 | `+` | 加算 |
| 算術演算子 | `-` | 減算 |
| 算術演算子 | `*` | 乗算 |
| 算術演算子 | `/` | 除算 |
| 関係子 | `<` | 小なり比較 |
| 関係子 | `>` | 大なり比較 |
| 関係子 | `=` | 等値比較 |
| 関係子 | `<=` | 以下比較 |
| 関係子 | `>=` | 以上比較 |
| 関係子 | `<>` | 非等値比較 |
| 真偽 | `1` | 真 |
| 真偽 | `0` | 偽 |
| 変数 | `A` から `Z` | 1 文字変数 |
| 配列変数 | `@(e)` | 添字 `0` からメモリ残量に応じた範囲の配列要素 |
| 配列変数 | `%(e)` | `@` を入力できないキーボード向けの入力時別名。内部では `@(e)` として扱う |
| 数値 | `-32768` から `32767` | 符号付き整数 |
| 文字列定数 | `"ABC"` | 二重引用符で囲む文字列 |
| 文字列定数 | `'ABC'` | アポストロフで囲む文字列 |
| 16進数定数 | `$00` から `$FF` | 1 バイト定数 |
| 16進数定数 | `$0000` から `$FFFF` | 2 バイト定数 |

**関数と特殊項目**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| 関数 | `ABS(e)` | `e` の絶対値を返す |
| 関数 | `RND(e)` | `0` から `e-1` までの一様乱数を返す |
| 関数 | `MOD(e1,e2)` | `e1 ÷ e2` の剰余を返す |
| 関数 | `USR(e)` | `e` で示される 2 バイト値を機械語サブルーチン先頭番地として呼び出す |
| 関数 | `USR(e1,e2)` | `e1` を PC、`e2` を IX にセットして機械語とリンクする |
| 関数 | `USR(e1,e2,e3)` | `e1` を PC、`e2` を IX、`e3` の下位を A、上位を B にセットする |
| 関数 | `PEEK` 相当 | `v=#(e)` として、絶対番地 `e` の内容 1 バイトを参照する |
| 関数 | `POKE` 相当 | `#(e1)=e2` として、`e2` の下位 1 バイトを絶対番地 `e1` に格納する |
| 関数 | `CHR(e)` | 10 進または 16 進の文字コードを ASCII 文字に変換する |
| 関数 | `TAB(e)` | 印字位置を `e` 桁目まで進める。連続使用時に `e` が上昇順でない場合は無視される |

**エラー処理**

| 種別 | 記法 | 内容 |
| --- | --- | --- |
| 表示 | `ERROR n` | direct mode ではエラー番号だけを表示する |
| 表示 | `ERROR n` + `行番号 文` | run mode ではエラー番号に続けてエラー発生行を表示する |
| エラー | `100 INPUT ERROR` | 入力データの属性またはサイズが誤っている |
| エラー | `110 MEMORY SIZE OVER` | プログラムまたは配列が大きすぎる |
| エラー | `120 INVALID LINE NUMBER` | 行番号に誤りがある |
| エラー | `130 PRINT ERROR` | `PRINT` 文、または `INPUT` / `PRINT` / `STOP` に続く文字列定数に誤りがある |
| エラー | `140 ZERO DIVIDE` | 0 除算、`RND(e)` の `e=0`、`MOD(e1,e2)` の `e2=0` |
| エラー | `150 EXPRESSION IS TOO COMPLEX` | 括弧の利用が多すぎる |
| エラー | `160 ILLEGAL ARITHMETIC` | 算術式に誤りがある |
| エラー | `170 MOD ERROR` | `MOD(e1,e2)` の使い方が誤っている |
| エラー | `180 UNRECOGNIZED STATEMENT` | 解釈不能な文である |
| エラー | `190 SUBROUTINE ERROR` | サブルーチン定義に誤りがあるか、ネスティングが深すぎる |
| エラー | `200 LINE NUMBER NOT FOUND` | 行番号が見つからない |
| エラー | `210 FOR ERROR` | `FOR` の使い方が誤っているか、`FOR` / `NEXT` のネスティングが深すぎる |
| エラー | `220 NEXT ERROR` | `FOR` で定義されていない `NEXT` 文がある |

## テスト

```bash
pytest -q
```

テストでは主に次を確認しています。

- `dendai-tiny-basic.dump` から生成したバイナリ、逆アセンブル、quickload イメージの整合性
- `LIST`, `RUN`, `LET`, `PRINT`, `INPUT`, `GOSUB`, `STOP`, `NEW`, `EX` / `EXIT` などの基本操作
- `FOR` / `NEXT`, `IF`, `MOD(`, `ABS(`, `CHR(`, `TAB(`, `#(addr)` などの制御構文と式
- `AUTO n` の prompt と `USR(` の機械語リンク動作
- `mp_array.bas`, `mp_addsub.bas`, `mp_scale.bas`, `mp_div_small.bas`, `pi-010.bas` のデモ実行

## 確認済み動作

以下は、上の仕様のうち現行の dump とハーネスで回帰テストまたは実行確認できている項目です。

- `RUN`, `LIST`, `LET`, `GOSUB` / `RET` / `RETURN`, `REM`, `STOP`, `NEW`, `EX` / `EXIT`
- `PRINT` の数値、多桁数値、文字列、`,` / `;`, `/`, `MOD(`, `ABS(`, `CHR(`, `TAB(`, `#(addr)`
- `INPUT A`, `INPUT A,B` とその短縮形 `IN` / `PR`
- `FOR` / `NEXT` の `STEP` あり、`STEP` 省略、入れ子、`GOSUB` をまたぐ組み合わせ。dump 実動作としては負 `STEP` も確認済み
- `mp_addsub.bas`, `mp_scale.bas`, `mp_div_small.bas` が使う `FOR` / `NEXT` と `#(addr)` ベースの multi-precision 処理
- `AUTO n` の番号付き prompt
- `USR(e)` / `USR(e1,e2)` / `USR(e1,e2,e3)` の機械語呼び出しとレジスタ受け渡し
- `#(addr)=expr` によるメモリ書き込み
- エラー時の `ERROR n` 表示と `READY` への復帰

## ハーネスとBASIC本体の責務

Pythonは6800命令の実行、メモリ、モニタの文字入出力・終了、トレースと実行上限を担当します。
モニタの入力要求時にだけ次の入力を渡し、出力の `#` / `?` や `AUTO` の行番号から入力時機を推測しません。
ホストの行末をCRへ変換する以外、BASICソースを書き換えません。
構文・式・数値範囲・プログラム容量・エラー番号はBASIC本体に任せます。
Ctrl-CもPCの強制変更ではなく、文字 `$03` を渡して本体の中断処理を通します。
本体が入力状態を確認する地点で中断するため、入力を確認しないUSR機械語ループを強制脱出する機能ではありません。

従来のPython独自処理を撤去したため、以下の違いがあります。

- 即時文への `:END` 自動追加、16進数の10進数化、`LET #(...)` のLET削除は行いません。
- `INPUT "A",A,"B",B` の独自展開は廃止しました。複数のプロンプトには `INPUT "A",A:INPUT "B",B` と書きます。
- `INPUT` の値は本体が式として評価します。`1+2` は3、`32768` は16ビット値の-32768です。Pythonから範囲エラーを捏造しません。
- 不正な文字列や複雑な式は登録時にPythonで拒否せず、実行時に本体が判定します。
  従来の「括弧17段でERROR 150」はPython独自の制限でした。括弧17段だけの式は本体で正常に評価されます。

即時実行の行末には本体の修正も加えました。元の `$02CD` はNULの後を次の保存行とみなすため、
無変換の `PRINT 4` が4の出力後に `ERROR 180` になります。
生成時に `$02CD–$02CF` を `JMP $0963` に置換し、ヘルパー `$0963–$0975` で
コロンなら次の文、NULかつ入力バッファ（Xの上位バイトが0）ならREADY、
それ以外なら次の保存行へ進めます。入力領域はページ0、保存プログラムは `$0980` 以降という本体の配置に基づきます。
これは転記訂正ではなく動作修正です。AUTOヘルパー `$0950–$0962` と保存領域には重なりません。

## 制限

- `AUTO n` は raw dump のままだと `n - 10` を保存したあと通常のコマンド処理へ戻ってしまい、`AUTO 10` が `ERROR 180` になります。生成物では `scripts/normalize_dump.py` の helper patch により `$019F` の呼び出し先を `$0950` へ差し替え、`10 `、`20 `、... の番号付き prompt へ入るようにしています。
- 配列添字処理は raw dump の `$0629` で `$054E` を呼んでおり、ソース位置を示す X が式スタックの位置に変わって `ERROR 180` になります。生成時に `$062B` を `$4E` から `$65` へ補正して `$0565` を呼び、ソース位置を保持します。元ダンプは変更していません。`@(e)` / `%(e)` は本体の符号付き2バイト配列として扱い、絶対アドレスの1バイト参照 `#(e)` とは区別します。
  掲載値 `$4E` と周辺命令はスキャンと一致します。命令列の解析と独立した6800 CPUコアでの実行により、掲載コードの不具合と確認しました。本README末尾の「掲載ダンプの配列処理の検証」を参照してください。
- CPU は BASIC 本体とテスト済みの `USR` ルーチンに必要な命令を対象としています。`DAA`、`SWI` などの未対応命令は明示的に停止し、周辺回路・実機タイミング・ROM monitor 全体は再現しません。
- プログラム容量は BASIC 本体のメモリ検査で判定します。Python 側で入力行のサイズを累積する処理はなく、`NEW`、行の削除・置換、入力拒否を本体の動作に従って扱います。
- ハーネスはカセット・テープ入出力を持たないため、`LOAD` の実機動作は再現していません。
- `INPUT` については、README で確認済みとして挙げているのは数値変数入力です。
- monitor 制御 byte `0xFF` / `0x7F` / `0x02` / `0x03` は transcript では非表示扱いです。

## ライセンス

- `dendai-tiny-basic.dump` 以外のこのリポジトリの内容は MIT License です。
- `dendai-tiny-basic.dump` は MIT License の対象外です。
- `dendai-tiny-basic.dump` の出典と権利上の注意は、この README 先頭の書誌情報と引用を参照してください。

## ファイル構成

- [`dendai-tiny-basic.dump`](/root/work/dendai-tiny-basic/dendai-tiny-basic.dump): 元のダンプ
- [`dendai-tiny-basic.asm`](/root/work/dendai-tiny-basic/dendai-tiny-basic.asm): 現在の逆アセンブル
- [`demos/`](/root/work/dendai-tiny-basic/demos): BASIC デモ集
  - [`demos/sample.bas`](/root/work/dendai-tiny-basic/demos/sample.bas): サンプル BASIC プログラム
  - [`demos/mp_array.bas`](/root/work/dendai-tiny-basic/demos/mp_array.bas): 配列変数と `#(addr)` の基本動作デモ
  - [`demos/mp_addsub.bas`](/root/work/dendai-tiny-basic/demos/mp_addsub.bas): multi-precision 加減算デモ
  - [`demos/mp_scale.bas`](/root/work/dendai-tiny-basic/demos/mp_scale.bas): multi-precision 倍算デモ
  - [`demos/mp_div_small.bas`](/root/work/dendai-tiny-basic/demos/mp_div_small.bas): multi-precision 除算デモ
  - [`demos/pi-010.bas`](/root/work/dendai-tiny-basic/demos/pi-010.bas): 10 桁円周率デモ
  - [`demos/pi-050.bas`](/root/work/dendai-tiny-basic/demos/pi-050.bas): 50 桁円周率デモ
  - [`demos/pi-100.bas`](/root/work/dendai-tiny-basic/demos/pi-100.bas): 100 桁円周率デモ
- [`scripts/normalize_dump.py`](/root/work/dendai-tiny-basic/scripts/normalize_dump.py): dump を raw binary に正規化
- [`scripts/disassemble.py`](/root/work/dendai-tiny-basic/scripts/disassemble.py): 逆アセンブル生成
- [`scripts/run_harness.py`](/root/work/dendai-tiny-basic/scripts/run_harness.py): 6800 ハーネス実行
- [`scripts/update_artifacts.py`](/root/work/dendai-tiny-basic/scripts/update_artifacts.py): 生成物更新と整合性確認

## 掲載ダンプの配列処理の検証

### 結論

スキャン掲載値 `$062B = $4E` は転記と一致する。しかし、掲載命令
`$0629: JSR $054E` は配列添字の解析後にソース位置を失うため、配列処理の
呼び出し先として不適切である。`JSR $0565` への変更
（`$062B: $4E → $65`）を確定した動作修正として採用する。

これは原本の復元ではなく、掲載コードの不具合修正である。元の
`dendai-tiny-basic.dump` は保存し、`normalize_dump.py` で補正する。
印刷時の誤植か、印刷以前のプログラムの誤りかという発生経緯は、この技術的結論とは別である。

なお、ここで「元の `.dump` を保存」とは今回そのファイルを変更しないという意味である。
以前、この記録で述べた「既存 `.dump` には掲載値からの変更が含まれている」という
断定は、`$05F7` と `$0850` の判読ミスに基づいていたため撤回する。

### スキャンと命令列

[scan/2.png](scan/2.png) で `$04D2–$04D6`、`$054E–$0552`、
`$0565`、`$0629–$062E`、`$06A0–$06B3` を照合した。

```asm
; 掲載コード
0629  BD 05 4E   JSR $054E
062C  BD 06 A0   JSR $06A0

054E  8D 15      BSR $0565  ; 因子解析。値を式スタックに積む
0550  7E 04 D2   JMP $04D2
04D2  DF 0A      STX $0A    ; ソース位置を保存
04D4  DE 80      LDX $80    ; Xを式スタック位置に変更
04D6  39         RTS

06A0  DF 04      STX $04    ; 呼び出し元のXを保存
06A2  DE 80      LDX $80
06A4  8C 00 80   CPX #$0080
06A7  27 A3      BEQ $064C
06A9  A6 01      LDAA $01,X ; 値の下位バイト
06AB  E6 00      LDAB $00,X ; 値の上位バイト
06AD  08         INX
06AE  08         INX
06AF  DF 80      STX $80    ; 式スタックから値を取り出す
06B1  DE 04      LDX $04    ; 保存したXを復元。$0Aは参照しない
06B3  39         RTS
```

`$054E` は値の解析に加えて X を式スタックへ変更する。他の算術処理ではこの
動作を使うが、配列処理の呼び出し元は X がソース位置のままであることを要求する。
続く `$06A0` は X を保存・復元するだけで、`$0A` のソース位置を読み戻さない。
したがって添字の値は正しく取り出せても、次の `=` を読む位置が間違う。
`$0565` を直接呼ぶと、この不要な X の変更を避けられる。

### 独立した CPU 実装による確認

自作 Python の入力変換・プロンプト処理・疑似エラー生成を使わず、
LET のオペランド解析ルーチン `$0651` を直接実行した。
次の二つの CPU 実装で、下記のレジスタ遷移と結果が一致した。

- このリポジトリの `CPU6800`
- [EtchedPixels/EmulatorKit の 6800.c](https://github.com/EtchedPixels/EmulatorKit/blob/b145b9003d94af73f92cca7f73c0ab1c6be6951d/6800.c)、`CPU_6800` / `INTIO_NONE`

独立コアのコミットは `b145b9003d94af73f92cca7f73c0ab1c6be6951d`。
初期状態は以下のとおり。

- `$1000` に NUL 終端の `@(1)=12345` を配置し、`PC=$0651`、`X=$1000`。
- 式スタックポインタ `[$80]=$0080`、入力領域終端 `[$10]=$0070`。
- プログラム終端 `[$B8]=$0981`、利用可能メモリ終端 `[$BA]=$8003`。
- `SP=$9FFE`、`[$9FFF]=$0200` を復帰先とする。
- `$0200`（正常復帰）または `$0859`（エラー入口）で停止。

| 観測地点 | 掲載値 `$4E` | 補正値 `$65` |
| --- | --- | --- |
| `$062C`：添字解析後 | X=`$007E` | X=`$1004` |
| `$062F`：値を取り出した後 | X=`$007E`、B:A=`$0001` | X=`$1004`、B:A=`$0001` |
| `$0643`：配列アドレス算出後 | X=`$007E`、B:A=`$0984` | X=`$1004`、B:A=`$0984` |
| `$065A`：`=` の解析直前 | X=`$007E` | X=`$1004` |
| 結果 | `$0859` に到達、B=`180` | `$0200` に正常復帰、X=`$0984`、B:A=`$3039`（12345） |

`$1004` が `=` の位置であり、`$007E` は式スタックの位置である。
誤りは配列要素アドレスの計算でも数値の切り詰めでもなく、ソース位置の喪失である。

この初期状態と比較は
`tests/test_review_regressions.py::test_array_call_contract_without_source_translation`
に回帰テストとして保存した。独立コアでの検証は開発時の照合であり、
通常のテスト実行に外部 CPU コアは必要ない。

### 他の転記箇所が原因ではないかの再照合

`scan/1.png`、`scan/2.png`、`scan/3.png` を再確認し、
`scan/資料5 電大版Tiny BASICの概要.pdf` の PDF 7・8 ページ
（書籍の付録ページ (27)–(29)）から拡大表示して照合した。
OCR は候補確認に使い、下表の値は画像で確認した。

特に、別の転記誤りによってソース位置の復元が失われた可能性を確認した。

| 位置 | スキャン掲載値 | 現在の `.dump` | 意味 |
| --- | --- | --- | --- |
| `$04D2–$04D6` | `DF 0A DE 80 39` | 一致 | ソース位置を保存した後、Xを式スタック位置に変更して復帰 |
| `$054E–$0552` | `8D 15 7E 04 D2` | 一致 | `$0565` を呼んだ後、必ず `$04D2` へ進む |
| `$0629–$062E` | `BD 05 4E BD 06 A0` | 一致 | 問題の呼び出しと、続く値の取り出し |
| `$06A0–$06A3` | `DF 04 DE 80` | 一致 | 入ってきたXを `$04` に保存する |
| `$06B1–$06B3` | `DE 04 39` | 一致 | `$04` をXに戻す。`DE 0A 39` の転記誤りではない |
| `$0654–$065C` | `25 F6 97 03 D7 02 8D ED 8D` | 一致 | 配列アドレスを保存して `=` を読むまでに、Xをソース位置へ戻す命令はない |

加えて、他のコードの転記精度に依存しない最小実行を行った。
全メモリをゼロにした CPU に、画像で確認した以下の28バイトだけを配置した。

```text
04D2: DF 0A DE 80 39
062C: BD 06 A0
06A0: DF 04 DE 80 8C 00 80 27 A3 A6 01 E6 00 08 08 DF
06B0: 80 DE 04 39
```

初期値を `X=$1004`、`[$80]=$007E`、`[$007E]=$0001` とした。
`$04D2` から開始し、RTS の復帰先を `$062C` に置くと、
`$062F` 到達時の値は `1` だが X は `$007E` になる。
比較として `$062C` から直接開始すると、同じ値 `1` を得て X は `$1004` に保たれる。
両経路はそれぞれ15命令・12命令で完了し、これ以外のダンプの命令を実行しない。
つまり、他の転記箇所の違いを仮定しなくても、掲載されたラッパー自身がXを変更し、
後続処理がその誤ったXを保持することを示せる。

### `$05F7` と `$0850` の判読訂正

以前の記録では、この2箇所のスキャン掲載値を `BD` と誤読し、`.dump` との差分として
記載していた。ユーザーの指摘に基づき、掲載値をいずれも `8D` に訂正する。

| 位置 | スキャン | 現在の `.dump` | 確認事項 |
| --- | --- | --- | --- |
| `$05F7` | `8D` | `8D` | 一致。USR の処理 |
| `$0850` | `8D` | `8D` | 一致。出力処理 |

コミット `9848e88` に `$05F7` を `BD` から `8D` に変更した履歴はあるが、
スキャン掲載値も `8D` であるため、この変更を原本からの改変の証拠としては扱わない。
この2箇所に関する差分の指摘と、それを根拠にした原本との不一致の断定を撤回する。

本記録は全2128バイトの完全一致を保証するものではない。
一方、上記の原因を決める命令の照合と最小実行により、配列の問題を
「他の箇所の読み違いで発生した見かけの問題」とする説明は成立しない。
