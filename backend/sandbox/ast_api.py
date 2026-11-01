"""Trusted Python 2.7/3.x static AST-API inspection; never imports project code."""
from __future__ import print_function
import ast
import json
import os
import sys


def inspect(path):
    with open(path,'rb') as stream: tree=ast.parse(stream.read(),path)
    aliases=set(a.asname or a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names if a.name=='ast')
    errors=[]
    class Visitor(ast.NodeVisitor):
        def __init__(self): self.guards=set()
        def visit_Attribute(self,node):
            if isinstance(node.value,ast.Name) and node.value.id in aliases and not hasattr(ast,node.attr) and node.attr not in self.guards:
                errors.append({'file':os.path.relpath(path,'/src'),'line':node.lineno,'attribute':node.attr,'reason':'unguarded_missing_ast_attribute'})
            self.generic_visit(node)
        def visit_ImportFrom(self,node):
            if node.module=='ast':
                for name in node.names:
                    if not hasattr(ast,name.name) and name.name not in self.guards: errors.append({'file':os.path.relpath(path,'/src'),'line':node.lineno,'attribute':name.name,'reason':'missing_ast_import'})
        def visit_If(self,node):
            test=node.test; inverse=isinstance(test,ast.UnaryOp) and isinstance(test.op,ast.Not)
            call=test.operand if inverse else test
            guard=None
            if (isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='hasattr' and len(call.args)==2
                    and isinstance(call.args[0],ast.Name) and call.args[0].id in aliases and isinstance(call.args[1],ast.Str)):
                guard=call.args[1].s
            self.visit(test)
            saved=set(self.guards)
            for branch,enable in ((node.body,not inverse),(node.orelse,inverse)):
                self.guards=saved | ({guard} if guard and enable else set())
                for item in branch: self.visit(item)
            self.guards=saved
    Visitor().visit(tree)
    return errors


try:
    errors=[]
    for root,dirs,files in os.walk('/src'):
        dirs[:]=[d for d in dirs if not d.startswith('.') and d!='__pycache__']
        for name in files:
            if name.endswith('.py'): errors.extend(inspect(os.path.join(root,name)))
    print(json.dumps({'python':list(sys.version_info[:3]),'errors':errors,'scope':'direct ast references; limited static runtime-API check, not general compatibility proof'}))
except Exception:
    print(json.dumps({'error':'ast_api_inspection_failed'}));sys.exit(2)
