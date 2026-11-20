// Lists the public top-level types of every package that a system module of the
// running JDK exports without qualification, as JSON on standard output:
//
//   {"jdk": "<Runtime.version()>", "packages": {"java.util": ["AbstractList", ...], ...}}
//
// Packages and type names are sorted, so the output is the same on every run of
// one JDK. The graph stage reads the committed result to decide which classes
// are the JDK's (ADR-004, CBO).
//
// Run it with JDK 25 or newer (it uses an instance main and the class-file API):
// the newest JDK the project uses, which is at least as new as any JDK it
// supports. A newer JDK exports every package an older one does, so a newer list
// only recognises more JDK names. The JDK that ran is recorded in the "jdk" field
// of the committed list. Regenerate and commit the diff; the diff is the review
// of what the JDK added or removed:
//
//   java scripts/ListJdkTypes.java > codeograph/graph/jdk_types.json

import java.lang.classfile.ClassFile;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.lang.reflect.AccessFlag;
import java.nio.ByteBuffer;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

void main() throws Exception {
    SortedMap<String, SortedSet<String>> packages = new TreeMap<>();

    for (ModuleReference module : ModuleFinder.ofSystem().findAll()) {
        Set<String> exported = module.descriptor().exports().stream()
                .filter(export -> !export.isQualified())
                .map(ModuleDescriptor.Exports::source)
                .collect(Collectors.toSet());
        if (exported.isEmpty()) {
            continue;
        }
        try (ModuleReader reader = module.open()) {
            for (String resource : (Iterable<String>) reader.list()::iterator) {
                if (!resource.endsWith(".class")) {
                    continue;
                }
                int slash = resource.lastIndexOf('/');
                if (slash < 0) {
                    continue;
                }
                String packageName = resource.substring(0, slash).replace('/', '.');
                String simpleName = resource.substring(slash + 1, resource.length() - ".class".length());
                // A nested type's file name carries a '$'; package-info and module-info are not types.
                if (!exported.contains(packageName) || simpleName.contains("$")
                        || simpleName.equals("package-info") || simpleName.equals("module-info")) {
                    continue;
                }
                ByteBuffer bytes = reader.read(resource).orElseThrow();
                byte[] content = new byte[bytes.remaining()];
                bytes.get(content);
                reader.release(bytes);
                if (ClassFile.of().parse(content).flags().has(AccessFlag.PUBLIC)) {
                    packages.computeIfAbsent(packageName, p -> new TreeSet<>()).add(simpleName);
                }
            }
        }
    }

    StringBuilder out = new StringBuilder();
    out.append("{\"jdk\": \"").append(Runtime.version()).append("\", \"packages\": {\n");
    int remaining = packages.size();
    for (var entry : packages.entrySet()) {
        out.append("  \"").append(entry.getKey()).append("\": [");
        out.append(entry.getValue().stream().map(name -> "\"" + name + "\"").collect(Collectors.joining(", ")));
        out.append(--remaining > 0 ? "],\n" : "]\n");
    }
    out.append("}}\n");
    System.out.print(out);
}
