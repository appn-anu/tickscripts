#!/bin/zsh
for file in $(find load -type f -mtime -1); do
    filename=$(basename $file)
    taskname=$(basename $filename .tick)
    fullpath="/etc/kapacitor/load/tasks/$filename"
    echo "kapacitor define "$taskname" -tick "$fullpath
    docker exec tickstack_kapacitor_1 kapacitor define $taskname -tick $fullpath
    echo "kapacitor reload "$taskname
    docker exec kapacitor tickstack_kapacitor_1 reload $taskname
done