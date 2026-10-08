"""Export a cooked Blueprint function as preserved JSON and an annotated listing."""
import argparse,json,sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('package');parser.add_argument('function');parser.add_argument('--output',required=True)
args=parser.parse_args()
db=sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
row=db.execute('SELECT body,status FROM blueprint_scripts WHERE package=? AND name=?',(args.package,args.function)).fetchone()
if not row:raise SystemExit('Function not found; use query.py scripts to find an exact package/name.')
doc=json.loads(row[0]);output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
def obj(value):
    if not isinstance(value,dict):return str(value)
    return value.get('ObjectName',str(value))
def variable(value):
    if not isinstance(value,dict):return str(value)
    if 'Path' in value:return '.'.join(value['Path'])
    if 'Property' in value:return value['Property'].get('Name',str(value))
    return str(value)
def expr(value):
    if not isinstance(value,dict):return str(value)
    token=value.get('Token','?')
    if token in ('EX_LocalVariable','EX_InstanceVariable','EX_LocalOutVariable'):return variable(value['Variable'])
    if token in ('EX_IntConst','EX_FloatConst','EX_StringConst','EX_UnicodeStringConst','EX_NameConst'):return repr(value.get('Value'))
    if token in ('EX_IntZero','EX_IntOne','EX_True','EX_False','EX_Self','EX_NoObject','EX_Nothing'):return token[3:]
    if token=='EX_ObjectConst':return obj(value.get('Value'))
    if token in ('EX_Context','EX_Context_FailSilent','EX_ClassContext'):return expr(value['ObjectExpression'])+' -> '+expr(value['ContextExpression'])
    if 'Function' in value or 'FunctionName' in value:return obj(value.get('Function',value.get('FunctionName')))+'('+', '.join(expr(p) for p in value.get('Parameters',[]))+')'
    if token in ('EX_Let','EX_LetBool','EX_LetObj'):return expr(value['Variable'])+' = '+expr(value['Expression'])
    if token=='EX_LetValueOnPersistentFrame':return variable(value['DestinationProperty'])+' = '+expr(value['AssignmentExpression'])
    if token=='EX_ComputedJump':return 'computed_jump '+expr(value['CodeOffsetExpression'])
    if token=='EX_Jump':return 'jump L'+str(value['CodeOffset'])
    if token=='EX_JumpIfNot':return 'if_false '+expr(value['BooleanExpression'])+' jump L'+str(value['CodeOffset'])
    if token=='EX_PushExecutionFlow':return 'push_continuation L'+str(value['PushingAddress'])
    if token=='EX_PopExecutionFlow':return 'pop_continuation'
    if token=='EX_PopExecutionFlowIfNot':return 'if_false '+expr(value['BooleanExpression'])+' pop_continuation'
    if token=='EX_Return':return 'return '+expr(value['Expression'])
    if token=='EX_EndOfScript':return 'end_of_script'
    return json.dumps(value,separators=(',',':'))
listing='\n'.join(f"L{item['StatementIndex']}: {expr(item)}" for item in doc['ScriptBytecode'])
text=f"# {args.function}\n\nPackage: `{args.package}`. Parser status: `{row[1]}`.\n\nThis is a structural bytecode listing with candidate operand interpretations. The JSON preserves the parsed expressions; no runtime outcome is implied.\n\n```text\n{listing}\n```\n"
output.with_suffix('.md').write_text(text,encoding='utf-8')
output.with_suffix('.json').write_text(json.dumps(doc,indent=2),encoding='utf-8')
print(str(output.with_suffix('.md')));db.close()
