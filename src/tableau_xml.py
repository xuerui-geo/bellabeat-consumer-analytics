"""Generic helpers that write a Tableau workbook (.twb/.twbx with Hyper extracts) from tidy CSVs.
Adapted from my ecommerce-growth-analytics project, where this approach opens in Tableau Public."""
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TAB = ROOT / "tableau"
DATA_REL = "Data/tableau"
DATA = TAB / DATA_REL
DATA.mkdir(parents=True, exist_ok=True)
TITLES = {}

from tableauhyperapi import (Connection, CreateMode, HyperProcess, Inserter, SqlType, TableDefinition,  # noqa: E402
                             TableName, Telemetry)

EXTRACTS_REL = "Data/Extracts"
EXTRACTS = TAB / EXTRACTS_REL
EXTRACTS.mkdir(parents=True, exist_ok=True)


def write_hyper(csv_name, types):
    df = pd.read_csv(DATA / csv_name)
    sql = {"date": SqlType.date(), "integer": SqlType.big_int(), "real": SqlType.double(), "string": SqlType.text()}
    table = TableDefinition(TableName("Extract", "Extract"),
                            [TableDefinition.Column(c, sql[t]) for c, t in types.items()])
    path = EXTRACTS / csv_name.replace(".csv", ".hyper")
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                      parameters={"default_database_version": "0"}) as hp:
        with Connection(hp.endpoint, path, CreateMode.CREATE_AND_REPLACE) as con_h:
            con_h.catalog.create_schema("Extract")
            con_h.catalog.create_table(table)
            rows = []
            for rec in df.itertuples(index=False):
                row = []
                for (c, t), v in zip(types.items(), rec):
                    if pd.isna(v):
                        row.append(None)
                    elif t == "date":
                        row.append(pd.Timestamp(v).date())
                    elif t == "integer":
                        row.append(int(v))
                    elif t == "real":
                        row.append(float(v))
                    else:
                        row.append(str(v))
                rows.append(row)
            with Inserter(con_h, table) as ins:
                ins.add_rows(rows)
                ins.execute()
    return path


# =====================================================================  3. workbook XML
REMOTE = {"date": 133, "string": 129, "integer": 20, "real": 5}


def infer(series):
    if series.name in ("week", "date"):
        return "date"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "real"
    return "string"


class DS:
    """A text-file datasource plus calculated fields."""

    def __init__(self, key, file, caption, calcs=None, colors=None, formats=None):
        self.key, self.file, self.caption = key, file, caption
        self.df = pd.read_csv(DATA / file)
        self.types = {c: infer(self.df[c]) for c in self.df.columns}
        self.calcs = calcs or {}      # name -> (caption, formula, format)
        self.colors = colors or {}    # field -> {value: hex}
        self.formats = formats or {}  # field -> Tableau number format
        self.name = f"federated.{key}"

    def ref(self, inst):
        return f"[{self.name}].[{inst}]"

    def xml(self):
        table = self.file.replace(".csv", "#csv")
        cols = "\n".join(
            f"              <column datatype='{t}' name='{escape(c)}' ordinal='{i}' />"
            for i, (c, t) in enumerate(self.types.items()))
        meta = "\n".join(f"""          <metadata-record class='column'>
            <remote-name>{escape(c)}</remote-name>
            <remote-type>{REMOTE[t]}</remote-type>
            <local-name>[{escape(c)}]</local-name>
            <parent-name>[{self.file}]</parent-name>
            <remote-alias>{escape(c)}</remote-alias>
            <ordinal>{i}</ordinal>
            <local-type>{t}</local-type>
            <aggregation>{'Sum' if t in ('integer', 'real') else ('Year' if t == 'date' else 'Count')}</aggregation>
            <contains-null>true</contains-null>
          </metadata-record>""" for i, (c, t) in enumerate(self.types.items()))
        fields = []
        for c, t in self.types.items():
            if t in ("integer", "real"):
                fa = f" default-format='{self.formats[c]}'" if c in self.formats else ""
                fields.append(f"      <column datatype='{t}'{fa} name='[{c}]' role='measure' type='quantitative' />")
            elif t == "date":
                fields.append(f"      <column datatype='date' name='[{c}]' role='dimension' type='ordinal' />")
            else:
                fields.append(f"      <column datatype='string' name='[{c}]' role='dimension' type='nominal' />")
        for name, (cap, formula, fmt) in self.calcs.items():
            fmt_attr = f" default-format='{fmt}'" if fmt else ""
            fields.append(
                f"      <column caption='{escape(cap)}' datatype='real'{fmt_attr} name='[{name}]' role='measure' "
                f"type='quantitative'>\n        <calculation class='tableau' formula='{escape(formula, {chr(39): '&apos;'})}' />\n"
                f"      </column>")
        style = ""
        if self.colors:
            rules = []
            for field, mapping in self.colors.items():
                maps = "\n".join(
                    f"          <map to='{hx}'>\n            <bucket>&quot;{escape(v)}&quot;</bucket>\n          </map>"
                    for v, hx in mapping.items())
                rules.append(f"        <encoding attr='color' field='[none:{field}:nk]' type='palette'>\n{maps}\n        </encoding>")
            style = "    <style>\n      <style-rule element='mark'>\n" + "\n".join(rules) + "\n      </style-rule>\n    </style>\n"
        hyper = self.file.replace(".csv", ".hyper")
        ex_meta = "\n".join(f"""            <metadata-record class='column'>
              <remote-name>{escape(c)}</remote-name>
              <remote-type>{REMOTE[t]}</remote-type>
              <local-name>[{escape(c)}]</local-name>
              <parent-name>[Extract]</parent-name>
              <remote-alias>{escape(c)}</remote-alias>
              <ordinal>{i}</ordinal>
              <local-type>{t}</local-type>
              <aggregation>{'Sum' if t in ('integer', 'real') else ('Year' if t == 'date' else 'Count')}</aggregation>
              <contains-null>true</contains-null>
            </metadata-record>""" for i, (c, t) in enumerate(self.types.items()))
        extract = f"""      <extract count='-1' enabled='true' units='records'>
        <connection access_mode='readonly' authentication='auth-none' author-locale='en_US' class='hyper' dbname='{EXTRACTS_REL}/{hyper}' default-settings='yes' schema='Extract' sslmode='' tablename='Extract' update-time='11/19/2026 08:00:00 PM' username='tableau_internal_user'>
          <relation name='Extract' table='[Extract].[Extract]' type='table' />
          <refresh increment-key='' incremental-updates='false' />
          <metadata-records>
{ex_meta}
          </metadata-records>
        </connection>
      </extract>
"""
        return f"""    <datasource caption='{escape(self.caption)}' inline='true' name='{self.name}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{self.file}' name='textscan.{self.key}'>
            <connection class='textscan' directory='{DATA_REL}' filename='{self.file}' password='' server='' />
          </named-connection>
        </named-connections>
        <relation connection='textscan.{self.key}' name='{self.file}' table='[{table}]' type='table'>
          <columns character-set='UTF-8' header='yes' locale='en_US' separator=','>
{cols}
          </columns>
        </relation>
        <metadata-records>
{meta}
        </metadata-records>
      </connection>
      <aliases enabled='yes' />
{chr(10).join(fields)}
{extract}      <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />
{style}    </datasource>"""


def inst(ds, spec):
    """spec like 'sum:gmv', 'none:segment', 'tdy:week', 'usr:Calculation_1' -> (instance name, xml)."""
    kind, field = spec.split(":", 1)
    if kind == "none":
        name, deriv, typ = f"none:{field}:nk", "None", "nominal"
    elif kind == "tdy":
        name, deriv, typ = f"tdy:{field}:qk", "Day-Trunc", "quantitative"
    elif kind == "usr":
        name, deriv, typ = f"usr:{field}:qk", "User", "quantitative"
    else:
        name, deriv, typ = f"{kind}:{field}:qk", {"sum": "Sum", "avg": "Avg"}[kind], "quantitative"
    xml = f"            <column-instance column='[{field}]' derivation='{deriv}' name='[{name}]' pivot='key' type='{typ}' />"
    return name, xml


def worksheet(title, ds, cols, rows, mark, color=None, label=None, sort_desc=None, label_fmt=None):
    specs = [s for s in cols + rows + [color, label] if s]
    deps, seen, insts = [], set(), {}
    for s in specs:
        n, x = inst(ds, s)
        insts[s] = n
        if n not in seen:
            deps.append(x)
            seen.add(n)
    fields_needed = {s.split(":", 1)[1] for s in specs}
    # base columns referenced inside calculated fields must also be declared
    for f in list(fields_needed):
        if f in ds.calcs:
            fields_needed |= set(re.findall(r"\[([^\]]+)\]", ds.calcs[f][1]))
    fields_needed = sorted(fields_needed)
    col_decl = []
    for f in fields_needed:
        if f in ds.calcs:
            cap, formula, fmt = ds.calcs[f]
            fmt_attr = f" default-format='{fmt}'" if fmt else ""
            col_decl.append(
                f"            <column caption='{escape(cap)}' datatype='real'{fmt_attr} name='[{f}]' role='measure' "
                f"type='quantitative'>\n              <calculation class='tableau' formula='{escape(formula, {chr(39): '&apos;'})}' />\n"
                f"            </column>")
        else:
            t = ds.types[f]
            role, typ = (("measure", "quantitative") if t in ("integer", "real")
                         else ("dimension", "ordinal" if t == "date" else "nominal"))
            fa = f" default-format='{ds.formats[f]}'" if f in ds.formats else ""
            col_decl.append(f"            <column datatype='{t}'{fa} name='[{f}]' role='{role}' type='{typ}' />")
    enc = []
    if color:
        enc.append(f"              <color column='{ds.ref(insts[color])}' />")
    if label:
        enc.append(f"              <text column='{ds.ref(insts[label])}' />")
    enc_xml = ("            <encodings>\n" + "\n".join(enc) + "\n            </encodings>\n") if enc else ""
    pane_style = ""
    if label:
        pane_style = ("            <style>\n              <style-rule element='mark'>\n"
                      "                <format attr='mark-labels-show' value='true' />\n"
                      "              </style-rule>\n            </style>\n")
    sort_xml = ""
    if sort_desc:
        dim, meas = sort_desc
        sort_xml = (f"          <sort class='computed' column='{ds.ref(insts[dim])}' direction='DESC' "
                    f"using='{ds.ref(insts[meas])}' />\n")

    def shelf(lst):
        refs = [ds.ref(insts[s]) for s in lst]
        if not refs:
            return ""
        out = refs[0]
        for r in refs[1:]:
            out = f"({out} / {r})"
        return out

    return f"""    <worksheet name='{escape(title)}'>
      <layout-options>
        <title>
          <formatted-text>
            <run bold='true' fontsize='12'>{escape(title)}</run>
          </formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption='{escape(ds.caption)}' name='{ds.name}' />
          </datasources>
          <datasource-dependencies datasource='{ds.name}'>
{chr(10).join(col_decl)}
{chr(10).join(deps)}
          </datasource-dependencies>
{sort_xml}          <aggregation value='true' />
        </view>
        <style />
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark}' />
{enc_xml}{pane_style}          </pane>
        </panes>
        <rows>{shelf(rows)}</rows>
        <cols>{shelf(cols)}</cols>
      </table>
    </worksheet>"""


def uuid_for(s):
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, s)).upper()


# ---------- dashboards: standard tiled layout (layout-basic > vertical flow > horizontal flows)
_ids = iter(range(100, 10000))


def sheet_zone(key, x, y, w, h):
    return f"<zone h='{h}' id='{next(_ids)}' name='{escape(TITLES[key])}' w='{w}' x='{x}' y='{y}' />"


def flow(direction, children, x, y, w, h):
    return (f"<zone h='{h}' id='{next(_ids)}' param='{direction}' type-v2='layout-flow' w='{w}' x='{x}' y='{y}'>"
            + "".join(children) + "</zone>")


def title_zone(title, sub, x, y, w, h):
    return (f"<zone h='{h}' id='{next(_ids)}' type-v2='text' w='{w}' x='{x}' y='{y}'>"
            f"<formatted-text><run bold='true' fontsize='16'>{escape(title)}</run><run>Æ&#10;</run>"
            f"<run fontcolor='#52514e' fontsize='10'>{escape(sub)}</run></formatted-text></zone>")


def row(items, y, h):
    """items: list of (key, width) or (['k1', 'k2'], width) for a vertical stack."""
    kids, x = [], 0
    for item, w in items:
        if isinstance(item, list):
            hh = h // len(item)
            sub = [sheet_zone(k, x, y + i * hh, w, hh if i < len(item) - 1 else h - hh * (len(item) - 1))
                   for i, k in enumerate(item)]
            kids.append(flow("vert", sub, x, y, w, h))
        else:
            kids.append(sheet_zone(item, x, y, w, h))
        x += w
    return flow("horz", kids, 0, y, 100000, h)


def dashboard(name, title, sub, rows_spec, with_text=True):
    th = 9000
    body_h = (100000 - th) // len(rows_spec)
    parts = [title_zone(title, sub, 0, 0, 100000, th)]
    for i, items in enumerate(rows_spec):
        h = body_h if i < len(rows_spec) - 1 else 100000 - th - body_h * (len(rows_spec) - 1)
        parts.append(row(items, th + i * body_h, h))
    body = flow("vert", parts, 0, 0, 100000, 100000)
    root = f"<zone h='100000' id='{next(_ids)}' type-v2='layout-basic' w='100000' x='0' y='0'>{body}</zone>"
    return f"""    <dashboard name='{escape(name)}'>
      <style />
      <size maxheight='900' maxwidth='1400' minheight='900' minwidth='1400' />
      <zones>
        {root}
      </zones>
    </dashboard>"""


def dash_keys(rows_spec):
    out = []
    for items in rows_spec:
        for item, _ in items:
            out += item if isinstance(item, list) else [item]
    return out


CARDS = """      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='2147483647'>
            <card type='columns' />
          </strip>
          <strip size='2147483647'>
            <card type='rows' />
          </strip>
          <strip size='31'>
            <card type='title' />
          </strip>
        </edge>
      </cards>"""


def ws_window(key, hidden=True):
    attr = "hidden='true'" if hidden else "maximized='true'"
    return f"    <window class='worksheet' {attr} name='{escape(TITLES[key])}'>\n{CARDS}\n    </window>"


def make_twb(ds_list, ws_list, dashes, wins):
    dash_block = f"  <dashboards>\n{chr(10).join(dashes)}\n  </dashboards>\n" if dashes else ""
    return f"""<?xml version='1.0' encoding='utf-8' ?>

<workbook original-version='18.1' source-build='2023.1.0 (20231.23.0310.1045)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{chr(10).join(d.xml() for d in ds_list)}
  </datasources>
  <worksheets>
{chr(10).join(ws_list)}
  </worksheets>
{dash_block}  <windows source-height='30'>
{chr(10).join(wins)}
  </windows>
</workbook>
"""


def package(name, twb_text, csv_files):
    twb_path = TAB / f"{name}.twb"
    twb_path.write_text(twb_text, encoding="utf-8")
    twbx_path = TAB / f"{name}.twbx"
    with zipfile.ZipFile(twbx_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(twb_path, twb_path.name)
        for f in csv_files:
            z.write(DATA / f, f"{DATA_REL}/{f}")
            h = f.replace(".csv", ".hyper")
            z.write(EXTRACTS / h, f"{EXTRACTS_REL}/{h}")
    return twb_path, twbx_path
