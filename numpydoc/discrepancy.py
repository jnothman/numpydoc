import re
import difflib
import inspect
import importlib
import sys

from .docscrape import NumpyDocString


def _get_doc_indent(doc):
    """Calculate indentation for docstring.

    Any whitespace that can be uniformly removed from the second line
    onwards is removed.

    Modified from CPython's inspect.cleandoc
    """
    try:
        lines = doc.expandtabs().split('\n')
    except UnicodeError:
        return None
    else:
        # Find minimum indentation of any non-blank lines after first line.
        margin = sys.maxsize
        for line in lines[1:]:
            content = len(line.lstrip())
            if content:
                indent = len(line) - content
                margin = min(margin, indent)
        # Remove indentation.
        if margin == sys.maxsize:
            margin = 0
        return margin


def _findclass(func):
    """

    From CPython's inspect module.
    """
    cls = sys.modules.get(func.__module__)
    if cls is None:
        return None
    for name in func.__qualname__.split('.')[:-1]:
        cls = getattr(cls, name)
    if not inspect.isclass(cls):
        return None
    return cls


def _finddoc_obj(obj):
    """

    From CPython's inspect module.
    """
    try:
        doc = obj.__doc__
    except AttributeError:
        return None
    if doc is not None:
        return obj

    if inspect.isclass(obj):
        for base in obj.__mro__:
            if base is not object:
                try:
                    doc = base.__doc__
                except AttributeError:
                    continue
                if doc is not None:
                    return base
        return None

    if inspect.ismethod(obj):
        name = obj.__func__.__name__
        self = obj.__self__
        if inspect.isclass(self) and \
           getattr(getattr(self, name, None), '__func__') is obj.__func__:
            # classmethod
            cls = self
        else:
            cls = self.__class__
    elif inspect.isfunction(obj):
        name = obj.__name__
        cls = _findclass(obj)
        if cls is None or getattr(cls, name) is not obj:
            return None
    elif inspect.isbuiltin(obj):
        name = obj.__name__
        self = obj.__self__
        if inspect.isclass(self) and \
           self.__qualname__ + '.' + name == obj.__qualname__:
            # classmethod
            cls = self
        else:
            cls = self.__class__
    # Should be tested before isdatadescriptor().
    elif isinstance(obj, property):
        func = obj.fget
        name = func.__name__
        cls = _findclass(func)
        if cls is None or getattr(cls, name) is not obj:
            return None
    elif self.ismethoddescriptor(obj) or self.isdatadescriptor(obj):
        name = obj.__name__
        cls = obj.__objclass__
        if getattr(cls, name) is not obj:
            return None
    else:
        return None

    for base in cls.__mro__:
        try:
            doc = getattr(base, name).__doc__
        except AttributeError:
            continue
        if doc is not None:
            return base
    return None


def get_docstring_source(obj, check_match=True):
    """Attempts to locate the docstring for an object in source code

    Parameters
    ----------
    obj : object
        Object with the target docstring
    check_match : bool
        If True (default), raises an error if the docstring and that found do
        not exactly match.

    Returns
    -------
    resolved_obj : object
        The object where the input object has its docstring defined
    match_groups : dict
        Keys 'prefix', 'content' and 'suffix' split the ``resolved_obj``'s code
        into the docstring content and that which precedes and follows it.
    """
    resolved_obj = _finddoc_obj(obj)
    orig_doc = resolved_obj.__doc__
    if orig_doc is None:
        raise ValueError('Could not find __doc__ for {0!r}'.format(obj))

    lines, file_offset = inspect.getsourcelines(obj)
    orig_code = ''.join(lines)

    # This is a brittle way to find the docstring:
    # * only admits a single triple-quoted string
    # * assumes the first triple-quoted string in the function definition
    #   (including signature) is docstring
    # * does not handle escaping
    match = re.search(r'''
      ^
      (?P<prefix>
        .*?
        ^\s+[uU]?[rR]?(?P<quote>"""|''\')
        \s*
      )
      (?P<content>\S.*?)
      (?P<suffix>
        \s*
        (?P=quote)
        .*
      )
      $
      ''', orig_code, re.MULTILINE | re.DOTALL | re.VERBOSE)
    if match is None:
        raise NotImplementedError('Could not get __doc__ by regex.')
    if check_match and orig_doc.strip() != match.group('content'):
        raise NotImplementedError('Could not match __doc__ by regex.'
                                  'This may be due to use of \\ escapes.')
    return match.groupdict()


def get_docstring_line_range(obj, check_match=True):
    """

    Parameters
    ----------
    obj : object
        Object with the target docstring
    check_match : bool
        If True (default), raises an error if the docstring and that found do
        not exactly match.

    Returns
    -------
    path : str
        Path to file where obj's docstring is defined
    start_line : int
        Line number where obj's docstring begins
    stop_line : int
        Line number of closing quote for docstring
    """
    resolved_obj, match = get_docstring_source(obj, check_match=check_match)
    path = inspect.getsourcefile(obj)
    _, file_offset = inspect.getsourcelines(obj)
    start = file_offset + match['prefix'].count('\n')
    stop = start + match['content'].count('\n')
    return path, start, stop


def build_docstring_diff(obj, updated_docstring, path=None):
    resolved_obj, match = get_docstring_source(obj)
    orig_doc = resolved_obj.__doc__

    prefix = match['prefix']
    suffix = match['suffix']
    indent = ' ' * _get_doc_indent(orig_doc)

    if path is None:
        path = inspect.getsourcefile(resolved_obj)

    lines, file_offset = inspect.getsourcelines(obj)
    file_offset = '\n' * (file_offset - 1)
    diff_from = file_offset + ''.join(lines)
    updated_lines = updated_docstring.split('\n')
    if updated_lines:
        updated_lines = updated_lines[:1] + [indent + l
                                             for l in updated_lines[1:]]
        out_doc = '\n'.join(updated_lines)
    else:
        out_doc = ''
    diff_to = file_offset + prefix + out_doc + suffix
    diff = difflib.unified_diff(diff_from.split('\n'), diff_to.split('\n'),
                                fromfile='a/' + path, tofile='b/' + path,
                                lineterm='',
                                n=2)  # n=2 should work for a non-empty obj
    return '\n'.join(diff)


def get_param_diff(obj, positional=(), keyword=(), section='Parameters',
                   path=None):
    """Propose changes to the docstring to match requirements

    Parameters
    ----------
    obj : function or class with numpydoc docstring
    positional : sequence of str, optional
        Sought positional argument names in order
    keyword : set of str, optional
        Sought keyword argument names for arbitrary order
    section : str, optional
        A :class:`NumpyDocString` section key which indicates a parameter list.
    path : str, optional
        The path that the diff is to patch. Defaults to source file.

    Returns
    -------
    diff : str
        A unified diff which patches the parameter list section to match
        the sought keywords. Keyword entries are removed if absent from
        ``positional`` and ``keyword``; reordered or inserted in the correct
        place according to ``positional``; and appended in alphabetical order
        if newly found in ``keyword``.

        If there is nothing to patch, the empty string is returned.
    """
    keyword = set(keyword)
    if keyword.intersection(positional):
        raise ValueError('`positional` and `keyword` should be '
                         'non-overlapping. Found intersection %s' %
                         keyword.intersection(positional))

    orig_doc = inspect.getdoc(obj)
    parsed_docstring = NumpyDocString(orig_doc)
    lines = orig_doc.split('\n')

    def get_lines(idx):
        start, length = parsed_docstring._line_spans[section, idx]
        return lines[start:start + length]

    section_start, param_list_length = parsed_docstring._line_spans[section]
    param_list_stop = section_start + param_list_length
    try:
        param_list_start, _ = parsed_docstring._line_spans[section, 0]
    except KeyError:
        # No params yet
        param_list_start = param_list_stop
    out = lines[:param_list_start]
    name_to_idx = dict((name, i)
                       for i, (name, _, _)
                       in enumerate(parsed_docstring[section]))

    # match and insert positionals
    for name in positional:
        if name in name_to_idx:
            out.extend(get_lines(name_to_idx[name]))
        else:
            # Insert: line contains name only
            out.append(name)

    # matched keywords
    positional = set(positional)
    for i, (name, _, _) in enumerate(parsed_docstring[section]):
        if name in positional:
            continue
        try:
            keyword.remove(name)
        except KeyError:
            continue
        out.extend(get_lines(i))

    # Insert remaining keywords
    out.extend(name for name in sorted(keyword))

    # FIXME: Be careful about following as may need to include closing of
    # docstring

    out.extend(lines[param_list_stop:])

    return build_docstring_diff(obj, '\n'.join(out), path=path)


def diff_parameters(obj, all_positional=False, remove=(), path=None):
    """Return a diff that updates docstring Parameters to the argspec

    Parameters
    ----------
    obj
    all_positional : boolean, optional
        If False (default), the order of documentation for arguments with
        default values  is ignored.  If True, documentation order will be
        matched to the argspec order.
    remove : collection of str
        These keyword arguments should not be documented despite appearing in
        argspec.
    path : str, optional
        The path that the diff is to patch. Defaults to source file.

    Returns
    -------
    diff : str
        A unified diff which patches the parameter list section to match
        the sought keywords.

        If there is nothing to patch, the empty string is returned.
    """
    if inspect.isclass(obj):
        # TODO: consider __new__?
        func = obj.__init__
    else:
        func = obj

    # TODO: use getfullargspec to support Py3 keyword-only args
    args, varargs_name, keywords_name, defaults = inspect.getargspec(func)

    # drop `self`
    if len(args) > 0 and args[0] == 'self':
        # TODO: consider `cls`
        args = args[1:]

    if all_positional or defaults is None:
        positional = args
        keyword = set()
    else:
        positional = args[:-len(defaults)]
        keyword = set(args[-len(defaults):])

    if varargs_name is not None:
        positional = list(positional) + [varargs_name]
    if keywords_name is not None:
        keyword.add(keywords_name)

    remove = set(remove)
    positional = [name for name in positional if name not in remove]
    keyword -= remove

    return get_param_diff(obj, positional=positional, keyword=keyword,
                          path=path)


def diff_member_parameters(module, all_positional=False, remove=(), path=None):
    """
    Parameters
    ----------
    module
    all_positional : boolean, optional
        If False (default), the order of documentation for arguments with
        default values  is ignored.  If True, documentation order will be
        matched to the argspec order.
    remove : collection of str
        These keyword arguments should not be documented despite appearing in
        argspec.
    path : str, optional
        The path that the diff is to patch. Defaults to source file per object.

    Reuturns
    --------
    unified_diff : str
    """
    diffs = []

    def append_diff(obj):
        try:
            diff = diff_parameters(obj, all_positional=all_positional,
                                   remove=remove, path=path)
        except Exception:
            # TODO: raise warning
            return

        if diff:
            diffs.append('For {0}.{1}:\n'
                         .format(inspect.getmodule(obj).__name__,
                                 obj.__name__))
            diffs.append(diff)

    for cname, cls in inspect.getmembers(module, inspect.isclass):
        if cname.startswith('_'):
            continue

        if hasattr(cls, '__init__'):
            append_diff(cls)

        for fname, func in inspect.getmembers(cls, inspect.isfunction):
            if fname == '__call__' or not fname.startswith('_'):
                append_diff(func)

    for fname, func in inspect.getmembers(module, inspect.isfunction):
        if not fname.startswith('_'):
            append_diff(func)

    return ''.join(diffs)


def main():
    """Print parameter diffs for the modules listed on the command-line
    """
    for name in sys.argv[1:]:
        module = importlib.import_module(name)
        sys.stdout.write(diff_member_parameters(module))


if __name__ == '__main__':
    main()
