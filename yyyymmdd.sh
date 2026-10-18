for f in GRMN????.txt ; do
    awk 'match($0, /[0-9]{2}\/[0-9]{2}\/[0-9]{4}/) {
           split(substr($0, RSTART, RLENGTH), parts, /[\/ ]/)

           $0 = substr($0, 1, RSTART - 1) \
                parts[3] "/" parts[1] "/" parts[2] \
                substr($0, RSTART + RLENGTH)
         }
         {print}' < $f > ${f#.txt}-yyyymmdd.txt
done
