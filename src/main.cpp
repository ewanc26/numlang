#include <cctype>
#include <cerrno>
#include <climits>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <sys/wait.h>
#include <utility>
#include <vector>

namespace {
struct Token {
    enum class Kind { Number, String, Character, Variable, Symbol } kind;
    std::string text;
    double number = 0;
    long long integer = 0;
    bool opcode = false;
    int line = 1, column = 1;
};
std::string c_quote(const std::string &s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            case '\0': out += "\\000"; break;
            default:
                if (c < 32 || c >= 127) {
                    const char d[] = "01234567";
                    out += '\\'; out += d[(c >> 6) & 7]; out += d[(c >> 3) & 7]; out += d[c & 7];
                } else out += static_cast<char>(c);
        }
    }
    return out + "\"";
}
class Lexer {
public:
    explicit Lexer(const std::string &s) : source(s) {}
    std::vector<Token> run() {
        std::vector<Token> out;
        while (!eof()) {
            if (std::isspace(static_cast<unsigned char>(peek()))) { advance(); continue; }
            if (peek() == '#') { while (!eof() && peek() != '\n') advance(); continue; }
            int line = ln, col = column;
            if (peek() == '"') { out.push_back(string_token(line,col)); continue; }
            if (peek() == '\'') { out.push_back(char_token(line,col)); continue; }
            if (std::isdigit(static_cast<unsigned char>(peek()))) { out.push_back(number_token(line,col)); continue; }
            if (peek() == '|' && std::isdigit(static_cast<unsigned char>(peek(1)))) {
                advance(); std::string n;
                while (std::isdigit(static_cast<unsigned char>(peek()))) n += advance();
                Token t{Token::Kind::Variable,n}; t.integer=std::stoll(n); t.line=line; t.column=col; out.push_back(t); continue;
            }
            Token t{Token::Kind::Symbol,std::string(1,advance())}; t.line=line; t.column=col; out.push_back(t);
        }
        return out;
    }
private:
    bool eof() const { return pos >= source.size(); }
    char peek(size_t n=0) const { return pos+n < source.size() ? source[pos+n] : '\0'; }
    char advance() {
        if (eof()) return '\0';
        char c=source[pos++]; if(c=='\n'){++ln;column=1;}else ++column; return c;
    }
    Token string_token(int line,int col) {
        advance(); std::string s;
        while(!eof() && peek()!='"') {
            char c=advance();
            if(c!='\\'){s+=c;continue;}
            if(eof()) throw std::runtime_error("unterminated string escape at line "+std::to_string(line));
            char e=advance();
            switch(e) {
                case 'n':s+='\n';break; case 'r':s+='\r';break; case 't':s+='\t';break;
                case 'b':s+='\b';break; case 'f':s+='\f';break; case 'v':s+='\v';break;
                case 'a':s+='\a';break; case '\\':s+='\\';break; case '"':s+='"';break;
                case '\'':s+='\'';break; case '0':s+='\0';break;
                case 'x': {
                    int v=0,n=0;
                    while(n<2 && std::isxdigit(static_cast<unsigned char>(peek()))) {
                        char h=advance(); v=v*16+(h>='0'&&h<='9'?h-'0':std::tolower(static_cast<unsigned char>(h))-'a'+10); ++n;
                    }
                    if(!n) throw std::runtime_error("empty hex escape at line "+std::to_string(line));
                    s+=static_cast<char>(v); break;
                }
                default:
                    if(e>='0'&&e<='7'){int v=e-'0';for(int i=0;i<2&&peek()>='0'&&peek()<='7';++i)v=v*8+advance()-'0';s+=static_cast<char>(v);}
                    else throw std::runtime_error("unsupported escape at line "+std::to_string(line));
            }
        }
        if(eof()) throw std::runtime_error("unterminated string at line "+std::to_string(line));
        advance(); Token t{Token::Kind::String,s}; t.line=line;t.column=col;return t;
    }
    Token char_token(int line,int col) {
        advance(); if(eof()) throw std::runtime_error("unterminated character literal at line "+std::to_string(line));
        unsigned char v=static_cast<unsigned char>(advance());
        if(v=='\\') {
            if(eof()) throw std::runtime_error("unterminated character escape at line "+std::to_string(line));
            char e=advance();
            switch(e){case 'n':v='\n';break;case 'r':v='\r';break;case 't':v='\t';break;case '\\':v='\\';break;case '\'':v='\'';break;case '"':v='"';break;case '0':v=0;break;default:throw std::runtime_error("unsupported character escape at line "+std::to_string(line));}
        }
        if(peek()!='\'') throw std::runtime_error("character literal must contain one character at line "+std::to_string(line));
        advance(); Token t{Token::Kind::Character,std::string(1,static_cast<char>(v))};t.integer=v;t.line=line;t.column=col;return t;
    }
    Token number_token(int line,int col) {
        std::string s;
        while(!eof() && (std::isalnum(static_cast<unsigned char>(peek()))||peek()=='.'||
              ((peek()=='+'||peek()=='-')&&!s.empty()&&(s.back()=='e'||s.back()=='E')))) s+=advance();

        auto valid_suffix = [](const std::string &x) {
            return x.empty() || x=="u" || x=="U" || x=="l" || x=="L" ||
                x=="ll" || x=="LL" || x=="ul" || x=="uL" || x=="ull" || x=="uLL" ||
                x=="UL" || x=="Ul" || x=="Ull" || x=="ULL" ||
                x=="lu" || x=="lU" || x=="Lu" || x=="LU" ||
                x=="llu" || x=="llU" || x=="LLu" || x=="LLU";
        };
        const bool hex = s.size()>2 && s[0]=='0' && (s[1]=='x'||s[1]=='X');
        const bool binary = s.size()>2 && s[0]=='0' && (s[1]=='b'||s[1]=='B');
        long long iv=0;
        double dv=0;
        bool fp=false;
        std::string suffix;
        if(binary) {
            size_t end=2;
            while(end<s.size()&&(s[end]=='0'||s[end]=='1')) ++end;
            if(end==2) throw std::runtime_error("invalid binary literal at line "+std::to_string(line));
            suffix=s.substr(end);
            if(!valid_suffix(suffix)) throw std::runtime_error("invalid binary literal at line "+std::to_string(line));
            for(size_t i=2;i<end;++i) {
                if(iv > (LLONG_MAX - (s[i]-'0')) / 2)
                    throw std::runtime_error("integer literal out of range at line "+std::to_string(line));
                iv=iv*2+s[i]-'0';
            }
            dv=static_cast<double>(iv);
        } else if(hex) {
            char *parsed=nullptr;
            errno=0;
            iv=std::strtoll(s.c_str(),&parsed,0);
            if(parsed==s.c_str()+2) throw std::runtime_error("invalid hexadecimal literal at line "+std::to_string(line));
            suffix=s.substr(static_cast<size_t>(parsed-s.c_str()));
            if(!valid_suffix(suffix)) throw std::runtime_error("invalid integer suffix at line "+std::to_string(line));
            if(errno==ERANGE) throw std::runtime_error("integer literal out of range at line "+std::to_string(line));
            dv=static_cast<double>(iv);
        } else {
            fp=s.find('.')!=std::string::npos||s.find('e')!=std::string::npos||s.find('E')!=std::string::npos;
            std::string n=s;
            if(!fp) {
                size_t suffix_start=n.size();
                while(suffix_start>0&&std::isalpha(static_cast<unsigned char>(n[suffix_start-1]))) --suffix_start;
                suffix=n.substr(suffix_start);
                if(!valid_suffix(suffix)) throw std::runtime_error("invalid integer suffix at line "+std::to_string(line));
                n.resize(suffix_start);
            }
            if(fp) {
                char *parsed=nullptr;
                dv=std::strtod(n.c_str(),&parsed);
                if(!parsed||parsed==n.c_str()||*parsed) throw std::runtime_error("invalid number at line "+std::to_string(line));
                if(!std::isfinite(dv)) throw std::runtime_error("number out of range at line "+std::to_string(line));
                // Floating-point literals are not opcode/integer tokens. Avoid converting
                // large finite doubles to long long, which can be undefined/out-of-range.
                iv=0;
            } else {
                char *parsed=nullptr;
                errno=0;
                iv=std::strtoll(n.c_str(),&parsed,0);
                if(!parsed||parsed==n.c_str()||*parsed) throw std::runtime_error("invalid integer at line "+std::to_string(line));
                if(errno==ERANGE) throw std::runtime_error("integer literal out of range at line "+std::to_string(line));
                dv=static_cast<double>(iv);
            }
        }
        Token t{Token::Kind::Number,s};
        t.number=dv;t.integer=iv;
        t.opcode=!hex&&!binary&&!fp&&suffix.empty()&&!(s.size()>1&&s[0]=='0');
        t.line=line;t.column=col;return t;
    }
    const std::string &source; size_t pos=0; int ln=1,column=1;
};
void binary(std::ostringstream &o,const char *op){o<<"{ double b=pop_value(), a=pop_value(); push_value(a "<<op<<" b); }\n";}
bool reserved_opcode(long long n) {
    switch(n) {
        case 20: case 28: case 30: case 50: case 51: case 52: case 53: case 55:
        case 60: case 61: case 62: case 63: case 64: return true;
        default: return (n >= 10 && n <= 19) || (n >= 21 && n <= 27) ||
                       n == 29 || (n >= 31 && n <= 49);
    }
}
bool opcode(std::ostringstream &o,long long n) {
    switch(n) {
        case 10:binary(o,"<");break;case 11:binary(o,">");break;case 12:binary(o,"==");break;case 13:binary(o,"!=");break;
        case 14:binary(o,"<=");break;case 15:binary(o,">=");break;
        case 16:o<<"{ double a=pop_value(); push_value(a); push_value(a); }\n";break;
        case 17:o<<"{ double b=pop_value(),a=pop_value(); push_value(b); push_value(a); }\n";break;
        case 18:o<<"(void)pop_value();\n";break;
        case 19:o<<"{ double b=pop_value(),a=pop_value(); push_value(a!=0||b!=0); }\n";break;
        case 21:o<<"push_value(fabs(pop_value()));\n";break;
        case 22:o<<"{double a=pop_value();if(a<0)fail_runtime(\"sqrt of negative value\");push_value(sqrt(a));}\n";break;
        case 23:o<<"push_value(floor(pop_value()));\n";break;case 24:o<<"push_value(ceil(pop_value()));\n";break;case 25:o<<"push_value(-pop_value());\n";break;
        case 26:o<<"{double b=pop_value(),a=pop_value();push_value(a<b?a:b);}\n";break;
        case 27:o<<"{double b=pop_value(),a=pop_value();push_value(a>b?a:b);}\n";break;
        case 29:o<<"{double b=pop_value(),a=pop_value();push_value(pow(a,b));}\n";break;
        case 31:o<<"push_value(log(pop_value()));\n";break;case 32:o<<"push_value(log10(pop_value()));\n";break;
        case 33:o<<"push_value(sin(pop_value()));\n";break;case 34:o<<"push_value(cos(pop_value()));\n";break;case 35:o<<"push_value(tan(pop_value()));\n";break;
        case 36:o<<"push_value(round(pop_value()));\n";break;case 37:o<<"push_value(trunc(pop_value()));\n";break;
        case 38:o<<"{int b=(int)pop_value(),a=(int)pop_value();if(!b)fail_runtime(\"integer remainder by zero\");push_value(a%b);}\n";break;
        case 39:o<<"{double b=pop_value(),a=pop_value();push_value(a!=0&&b!=0);}\n";break;
        case 40:o<<"{int b=(int)pop_value(),a=(int)pop_value();push_value(a&b);}\n";break;
        case 41:o<<"{int b=(int)pop_value(),a=(int)pop_value();push_value(a|b);}\n";break;
        case 42:o<<"{int b=(int)pop_value(),a=(int)pop_value();push_value(a^b);}\n";break;
        case 43:o<<"push_value(~(int)pop_value());\n";break;
        case 44:o<<"{int b=(int)pop_value(),a=(int)pop_value();if(b<0||b>=31)fail_runtime(\"invalid shift\");push_value(a<<b);}\n";break;
        case 45:o<<"{int b=(int)pop_value(),a=(int)pop_value();if(b<0||b>=31)fail_runtime(\"invalid shift\");push_value(a>>b);}\n";break;
        case 46:o<<"push_value(asin(pop_value()));\n";break;case 47:o<<"push_value(acos(pop_value()));\n";break;
        case 48:o<<"push_value(atan(pop_value()));\n";break;case 49:o<<"{double x=pop_value(),y=pop_value();push_value(atan2(y,x));}\n";break;
        default:return false;
    }
    return true;
}
std::string compile_c(const std::vector<Token> &tokens,int stack_size) {
    std::ostringstream body;
    for(const auto &t:tokens) {
        if(t.kind==Token::Kind::String) body<<"fwrite("<<c_quote(t.text)<<",1,"<<t.text.size()<<",stdout);\n";
        else if(t.kind==Token::Kind::Character) body<<"push_value("<<t.integer<<");\n";
        else if(t.kind==Token::Kind::Variable) {
            if(t.integer<0||t.integer>=100)throw std::runtime_error("variable index must be 0-99 at line "+std::to_string(t.line));
            body<<"push_value(variables["<<t.integer<<"]); \n";
        } else if(t.kind==Token::Kind::Number) {
            if(t.opcode) {
                if(opcode(body,t.integer)) continue;
                if(reserved_opcode(t.integer))
                    throw std::runtime_error("opcode "+std::to_string(t.integer)+" is not yet implemented at line "+std::to_string(t.line));
            }
            body<<"push_value("<<std::setprecision(17)<<t.number<<");\n";
        } else {
            const auto &s=t.text;
            if(s=="+")binary(body,"+");else if(s=="-")binary(body,"-");else if(s=="*")binary(body,"*");
            else if(s=="/")body<<"{double b=pop_value(),a=pop_value();if(b==0)fail_runtime(\"division by zero\");push_value(a/b);}\n";
            else if(s=="%")body<<"{double b=pop_value(),a=pop_value();if(b==0)fail_runtime(\"remainder by zero\");push_value(fmod(a,b));}\n";
            else if(s=="!")body<<"push_value(pop_value()==0?1:0);\n";
            else if(s=="&")body<<"{int i=(int)pop_value();double v=pop_value();if(i<0||i>=100)fail_runtime(\"variable index out of range\");variables[i]=v;}\n";
            else if(s=="|")body<<"printf(\"%.15g\\n\",pop_value());\n";
            else if(s=="^")body<<"putchar((unsigned char)pop_value());\n";
            else if(s=="?")body<<"{double v=0;if(scanf(\"%lf\",&v)!=1)fail_runtime(\"numeric input failed\");push_value(v);}\n";
            else throw std::runtime_error("unsupported token '"+s+"' at line "+std::to_string(t.line)+", column "+std::to_string(t.column));
        }
    }
    std::ostringstream c;
    c<<"#include <math.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <stddef.h>\n";
    c<<"#define STACK_CAPACITY "<<stack_size<<"\nstatic double stack_values[STACK_CAPACITY];\nstatic size_t stack_pointer=0;\nstatic double variables[100]={0};\n";
    c<<"static void fail_runtime(const char *m){fprintf(stderr,\"numlang runtime error: %s\\n\",m);exit(1);}\n";
    c<<"static void push_value(double v){if(stack_pointer>=STACK_CAPACITY)fail_runtime(\"stack overflow\");stack_values[stack_pointer++]=v;}\n";
    c<<"static double pop_value(void){if(!stack_pointer)fail_runtime(\"stack underflow\");return stack_values[--stack_pointer];}\n";
    c<<"int main(void){\n"<<body.str()<<"return 0;\n}\n";return c.str();
}
std::string shell_quote(const std::string &s){std::string q="'";for(char c:s){if(c=='\'')q+="'\\''";else q+=c;}return q+"'";}
std::filesystem::path make_temp(){auto base=std::filesystem::temp_directory_path();auto tick=std::chrono::steady_clock::now().time_since_epoch().count();std::random_device rd;for(int i=0;i<16;++i){auto p=base/("numlang-"+std::to_string(tick)+"-"+std::to_string(rd()));std::error_code e;if(std::filesystem::create_directory(p,e))return p;if(e&&e!=std::errc::file_exists)throw std::runtime_error(e.message());}throw std::runtime_error("cannot create temporary directory");}
struct Temp {std::filesystem::path path;~Temp(){std::error_code e;std::filesystem::remove_all(path,e);}};
int status(int s){if(s==-1)return 1;if(WIFEXITED(s))return WEXITSTATUS(s);if(WIFSIGNALED(s))return 128+WTERMSIG(s);return 1;}
}
int main(int argc,char **argv){
    if(argc<2){std::cerr<<"usage: numlangc <file.num> -o <output.c> | --run [--cc <compiler>] [--stack-size N]\n";return 1;}
    std::string input=argv[1],output,cc="cc";bool run=false;int stack_size=1000;
    for(int i=2;i<argc;++i){std::string a=argv[i];
        if(a=="-o"||a=="--output"){if(i+1>=argc){std::cerr<<"numlangc: "<<a<<" requires a path\n";return 1;}output=argv[++i];}
        else if(a=="--run")run=true;
        else if(a=="--cc"){if(i+1>=argc){std::cerr<<"numlangc: --cc requires a compiler path\n";return 1;}cc=argv[++i];}
        else if(a=="--stack-size"){if(i+1>=argc){std::cerr<<"numlangc: --stack-size requires a value\n";return 1;}try{stack_size=std::stoi(argv[++i]);}catch(...){std::cerr<<"numlangc: invalid stack size\n";return 1;}}
        else if(a=="--support"){std::cout<<"Support Numlang development:\n  Ko-fi: https://ko-fi.com/ewancroft\n  GitHub Sponsors: https://github.com/sponsors/ewanc26\n";return 0;}
        else{std::cerr<<"numlangc: unknown option "<<a<<"\n";return 1;}
    }
    if(stack_size<1||stack_size>10000000){std::cerr<<"numlangc: stack size must be between 1 and 10000000\n";return 1;}
    if(run&&!output.empty()){std::cerr<<"numlangc: choose either --run or -o/--output, not both\n";return 1;}
    if(!run&&output.empty()){std::cerr<<"numlangc: specify -o <output.c> or --run\n";return 1;}
    std::ifstream in(input);if(!in){std::cerr<<"numlangc: cannot read source file: "<<input<<"\n";return 1;}
    std::stringstream source;source<<in.rdbuf();
    try{
        const std::string source_text=source.str();
        Lexer lexer(source_text);const auto tokens=lexer.run();const std::string c=compile_c(tokens,stack_size);
        if(!run){std::ofstream out(output);if(!out){std::cerr<<"numlangc: cannot create output file: "<<output<<"\n";return 1;}out<<c;if(!out){std::cerr<<"numlangc: failed writing output file\n";return 1;}return 0;}
        Temp temp{make_temp()};auto cf=(temp.path/"numlang.c").string();auto exe=(temp.path/"numlang").string();
        {std::ofstream out(cf);if(!out)throw std::runtime_error("cannot write temporary C source");out<<c;}
        int r=std::system((shell_quote(cc)+" "+shell_quote(cf)+" -o "+shell_quote(exe)+" -lm").c_str());
        if(r==-1){std::cerr<<"numlangc: cannot start host C compiler\n";return 1;}if(status(r))return status(r);
        return status(std::system(shell_quote(exe).c_str()));
    }catch(const std::exception &e){std::cerr<<"numlangc: "<<e.what()<<"\n";return 1;}
}
