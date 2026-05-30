package com.example.qdsl;

import com.querydsl.jpa.impl.JPAQuery;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public class ItemRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Item> findExpensiveItems(Double minPrice) {
        QItem qItem = QItem.item;
        JPAQuery<Item> query = new JPAQuery<>(entityManager);
        
        return query.from(qItem)
                    .where(qItem.price.gt(minPrice))
                    .fetch();
    }
}
