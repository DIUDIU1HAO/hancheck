# 这个文件的注释里有中文标点，属于正常写作：逗号、句号、问号。
# hancheck 不应该对注释里的中文标点报警。
import json


def 计算总价(items):
    total = 0
    for item in items:
        total += item["price"]
    data = {"name": "张三"，"age": 18}
    print("完成：", total)
    return total


def bad_indent():
　　return 1


def invisible():
    total​ = 0
    return total


name = "张三”
phone = "13900001111"
idcard = "11010519491231002X"
card = "6222021234567894"
