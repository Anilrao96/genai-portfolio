"""Small authored function contracts; gold outputs stay outside the untrusted process."""
TASKS={
    'mean':{'title':'Mean with an empty-input rule','spec':'Write solve(data). data is a JSON list of numbers. Return its arithmetic mean; return zero for an empty list. Do not round the mean.',
            'inputs':[[],[2,4,6],[-4,4],[1,2]],'expected':[0,4,0,1.5],
            'starting_code':'def solve(data):\n    return sum(data) / len(data)\n'},
    'words':{'title':'Sorted unique words','spec':'Write solve(data). data is text. Extract runs of ASCII letters a-z case-insensitively, lowercase them, remove duplicates and return the words sorted alphabetically. Punctuation separates words.',
             'inputs':['Red red blue','Hello, WORLD! hello.','','one-two THREE'],'expected':[['blue','red'],['hello','world'],[],['one','three','two']],
             'starting_code':'def solve(data):\n    return sorted(set(data.lower().split()))\n'}
}
