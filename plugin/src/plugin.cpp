#include "clang/AST/AST.h"

#include <cmath>
#include <iostream>
#include <memory>
#include <vector>
#include <sstream>

#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"
#include "llvm/Support/CommandLine.h"
#include "clang/AST/RawCommentList.h"
#include "clang/Analysis/Analyses/Dominators.h"
#include "clang/Rewrite/Core/Rewriter.h"
#include "llvm/Support/raw_ostream.h"

#define DEBUG_STMT
using namespace clang;
using namespace clang::tooling;
static llvm::cl::OptionCategory MyToolCategory("my-tool options");
static llvm::cl::opt<std::string> OutputFile("o", llvm::cl::desc("Specify the output file"), llvm::cl::value_desc("filename"), llvm::cl::cat(MyToolCategory)); // does nothing right now
std::vector<std::string> comment_reqs;

class OptimizationVisitor : public RecursiveASTVisitor<OptimizationVisitor> {
 public:
  explicit OptimizationVisitor(ASTContext *Context) : context(Context) {}
  FunctionDecl *curr_func;
  bool VisitStmt(Stmt *stmt) {
        #ifdef DEBUG_STMT
        stmt->printPretty(llvm::outs(),
                          nullptr,
                          context->getPrintingPolicy());
        #endif
        return true; 
    }
    bool VisitFunctionDecl(FunctionDecl *f) {
        curr_func = f;
        #ifdef DEBUG_FUNC_DECL
        llvm::outs() << "adding global function " << f->getNameInfo().getName().getAsString();
        #endif
        return true;
    }

  
private:
  ASTContext *context;
};



class OptimizationConsumer : public clang::ASTConsumer {
 public:
  explicit OptimizationConsumer(ASTContext *Context) : visitor_(Context) {}

    virtual void HandleTranslationUnit(clang::ASTContext& context) {
        visitor_.TraverseDecl(context.getTranslationUnitDecl());
        auto comments = context.Comments.getCommentsInFile(
            context.getSourceManager().getMainFileID());
        if (!context.Comments.empty()) {
            for (auto it = comments->begin(); it != comments->end(); it++) {
                clang::RawComment* comment = it->second;
                std::string source = comment->getFormattedText(context.getSourceManager(),
                    context.getDiagnostics());
                comment_reqs.push_back(source);
            }
        }
    }

 private:
  OptimizationVisitor visitor_;
};

class OptimizationFrontendAction : public clang::ASTFrontendAction {
 public:
  virtual std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(
      clang::CompilerInstance &Compiler, llvm::StringRef InFile) {
    return std::make_unique<OptimizationConsumer>(&Compiler.getASTContext());
  }
};

int main(int argc, const char **argv) {
  auto ExpectedParser = CommonOptionsParser::create(argc, argv, MyToolCategory);
  if (!ExpectedParser) {
    llvm::errs() << ExpectedParser.takeError();
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpectedParser.get();

  ClangTool tool(OptionsParser.getCompilations(),
                 OptionsParser.getSourcePathList());

  OptimizationFrontendAction action;
  tool.run(newFrontendActionFactory<OptimizationFrontendAction>().get());
  
  return 0;
}